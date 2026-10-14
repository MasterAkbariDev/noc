import json
from dataclasses import dataclass

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.agents.grounding import ground_finding
from noc.agents.loop import AgentStats
from noc.agents.schemas import (
    Diagnosis,
    EvidenceRef,
    EvidenceStrength,
    Finding,
    FindingSeverity,
    Hypothesis,
    unknown_diagnosis,
)
from noc.db.models import AgentRun, AlertEvent, Incident, Target
from noc.db.session import transaction
from noc.domain.incident_status import IncidentStatus
from noc.orchestration.nodes import Update, incident_id_of
from noc.orchestration.runbook import (
    Runbook,
    RunbookEntry,
    entry_for,
    excerpt_for,
    load_runbook,
    resolve_arguments,
)
from noc.orchestration.runtime import Runtime
from noc.orchestration.state import IncidentState
from noc.store.briefs import target_ref
from noc.store.incidents import lock_incident, transition
from noc.store.investigations import (
    add_findings,
    finish_run,
    new_agent_run,
    persist_diagnosis,
)
from noc.tools.catalog import RUNBOOK
from noc.tools.registry import ToolResult
from noc.tools.spec import ToolContext

logger = structlog.get_logger(__name__)

FINDING_ID = "F1"
FIXED_CONFIDENCE = 1.0
NO_ENTRY = "The runbook has no entry for the alerts of this incident."
NO_EVIDENCE = "The runbook's evidence check did not return usable data."
SEVERITIES = {"critical": FindingSeverity.CRITICAL, "warning": FindingSeverity.WARNING}


@dataclass(frozen=True)
class RunbookInput:
    alertname: str
    entry: RunbookEntry
    arguments: dict[str, str]
    severity: str
    resource: str | None
    context: ToolContext


class RunbookNodes:
    def __init__(self, runtime: Runtime, runbook: Runbook | None = None) -> None:
        self._runtime = runtime
        self._sessions = runtime.sessions
        self._runbook = runbook or load_runbook()

    async def diagnose(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        async with transaction(self._sessions) as session:
            incident = await session.get_one(Incident, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            prepared = await self._prepare(session, incident)
            agent_run = new_agent_run(incident_id, RUNBOOK)
            session.add(agent_run)

        result = None if prepared is None else await self._gather(prepared)

        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            run = await session.merge(agent_run)
            await self._record(session, incident, run, prepared, result)
        return {"outcome": "diagnosed"}

    async def _prepare(self, session: AsyncSession, incident: Incident) -> RunbookInput | None:
        alerts = list(
            await session.scalars(
                select(AlertEvent)
                .where(AlertEvent.incident_id == incident.id)
                .order_by(AlertEvent.id)
            )
        )
        found = entry_for(self._runbook, [alert.alertname for alert in alerts])
        if found is None:
            return None
        alertname, entry = found
        alert = next(item for item in alerts if item.alertname == alertname)
        arguments = resolve_arguments(entry, alert.labels)
        if arguments is None:
            return None
        target = await session.get_one(Target, incident.target_id)
        context = ToolContext(
            incident_id=incident.id,
            agent=RUNBOOK,
            target=target_ref(target),
            trace_id=incident.trace_id,
        )
        return RunbookInput(
            alertname=alertname,
            entry=entry,
            arguments=arguments,
            severity=alert.severity,
            resource=alert.labels.get("resource"),
            context=context,
        )

    async def _gather(self, prepared: RunbookInput) -> ToolResult:
        return await self._runtime.registry.execute(
            prepared.entry.tool, json.dumps(prepared.arguments), prepared.context
        )

    async def _record(
        self,
        session: AsyncSession,
        incident: Incident,
        run: AgentRun,
        prepared: RunbookInput | None,
        result: ToolResult | None,
    ) -> None:
        diagnosis, findings = self._decide(prepared, result)
        finish_run(run, AgentStats(rounds=0, llm_calls=0, tool_calls=0 if result is None else 1))
        add_findings(session, incident.id, RUNBOOK, findings)
        await persist_diagnosis(session, incident, diagnosis, 0)
        await transition(session, incident, IncidentStatus.DIAGNOSED, RUNBOOK)

    def _decide(
        self, prepared: RunbookInput | None, result: ToolResult | None
    ) -> tuple[Diagnosis, list[Finding]]:
        if prepared is None:
            return unknown_diagnosis(NO_ENTRY), []
        if result is None or not result.ok or result.data is None:
            return unknown_diagnosis(NO_EVIDENCE), []
        finding = grounded_finding(prepared, result)
        if finding is None:
            return unknown_diagnosis(NO_EVIDENCE), []
        hypothesis = Hypothesis(
            root_cause_code=prepared.entry.root_cause,
            description=(
                f"The runbook maps {prepared.alertname} to {prepared.entry.root_cause.value}."
            ),
            confidence=FIXED_CONFIDENCE,
            supporting_findings=[FINDING_ID],
            affected_resource_id=prepared.resource,
        )
        return Diagnosis(hypotheses=[hypothesis]), [finding]


def grounded_finding(prepared: RunbookInput, result: ToolResult) -> Finding | None:
    finding = Finding(
        id=FINDING_ID,
        category=prepared.entry.category,
        summary=f"{prepared.alertname} fired and {prepared.entry.tool} answered.",
        severity=SEVERITIES.get(prepared.severity, FindingSeverity.INFO),
        evidence=[
            EvidenceRef(tool_call_ref=result.ref, excerpt=excerpt_for(prepared.entry, result.data))
        ],
        evidence_strength=EvidenceStrength.DIRECT,
        confidence=FIXED_CONFIDENCE,
    )
    return ground_finding(finding, {result.ref: result})
