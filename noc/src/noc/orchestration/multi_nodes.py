import uuid

import structlog
from langgraph.types import Send
from pydantic import TypeAdapter
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.agents.diagnosis import FindingView
from noc.agents.schemas import unknown_diagnosis
from noc.agents.supervisor import InvestigationPlan, plan_investigation
from noc.db.models import AgentRun, AlertEvent, FindingRow, Incident, IncidentEvent
from noc.db.session import transaction
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.llm.client import LLMError
from noc.orchestration.nodes import (
    SUPERVISOR,
    IncidentNodes,
    Update,
    escalation_reason_for,
    incident_id_of,
)
from noc.orchestration.runtime import Runtime
from noc.orchestration.state import IncidentState, SpecialistTask
from noc.store.briefs import load_investigation_input
from noc.store.incidents import add_event, lock_incident, transition
from noc.store.investigations import (
    add_findings,
    finding_view,
    finish_run,
    mark_run_failed,
    new_agent_run,
    persist_diagnosis,
)

logger = structlog.get_logger(__name__)

SPECIALIST = "specialist"
DIAGNOSE = "diagnose"
DIAGNOSIS_AGENT = "diagnosis"
PLANNED_EVENT = "investigation_planned"
UNAVAILABLE_EVENT = "specialist_unavailable"
FINISHED_EVENT = "specialist_finished"
FAILED_EVENT = "specialist_failed"
SPECIALIST_TASK = TypeAdapter(SpecialistTask)
NO_FINDINGS = "No specialist produced a grounded finding."
LLM_UNAVAILABLE_ERRORS = ("LLMUnavailable", "CassetteMiss")


async def stored_plan(session: AsyncSession, incident_id: uuid.UUID) -> InvestigationPlan | None:
    payload = await session.scalar(
        select(IncidentEvent.payload)
        .where(IncidentEvent.incident_id == incident_id, IncidentEvent.type == PLANNED_EVENT)
        .order_by(IncidentEvent.id.desc())
        .limit(1)
    )
    return None if payload is None else InvestigationPlan.model_validate(payload)


async def create_plan(
    session: AsyncSession, incident: Incident, runtime: Runtime
) -> InvestigationPlan:
    alertnames = list(
        await session.scalars(
            select(AlertEvent.alertname).where(AlertEvent.incident_id == incident.id).distinct()
        )
    )
    plan = plan_investigation(alertnames, runtime.routing)
    await add_event(session, incident.id, PLANNED_EVENT, SUPERVISOR, plan.model_dump(mode="json"))
    for name in plan.specialists:
        if name not in runtime.specialists:
            await add_event(
                session, incident.id, UNAVAILABLE_EVENT, SUPERVISOR, {"specialist": name}
            )
    incident.mode = "multi"
    return plan


async def succeeded_run_exists(session: AsyncSession, incident_id: uuid.UUID, agent: str) -> bool:
    found = await session.scalar(
        select(AgentRun.id)
        .where(
            AgentRun.incident_id == incident_id,
            AgentRun.agent == agent,
            AgentRun.status == "succeeded",
        )
        .limit(1)
    )
    return found is not None


async def dropped_specialist_findings(session: AsyncSession, incident_id: uuid.UUID) -> int:
    payloads = await session.scalars(
        select(IncidentEvent.payload).where(
            IncidentEvent.incident_id == incident_id, IncidentEvent.type == FINISHED_EVENT
        )
    )
    return sum(int(payload.get("dropped_findings", 0)) for payload in payloads)


async def investigation_failure(
    session: AsyncSession, incident_id: uuid.UUID
) -> EscalationReason | None:
    runs = list(
        await session.scalars(
            select(AgentRun).where(
                AgentRun.incident_id == incident_id, AgentRun.agent != DIAGNOSIS_AGENT
            )
        )
    )
    if not runs or any(run.status == "succeeded" for run in runs):
        return None
    failed = [run for run in runs if run.status == "failed"]
    if not failed:
        return None
    if all((run.error or "").startswith(LLM_UNAVAILABLE_ERRORS) for run in failed):
        return EscalationReason.LLM_UNAVAILABLE
    return EscalationReason.INVESTIGATION_FAILED


async def grounded_findings(session: AsyncSession, incident_id: uuid.UUID) -> list[FindingView]:
    rows = await session.scalars(
        select(FindingRow)
        .where(FindingRow.incident_id == incident_id, FindingRow.grounded.is_(True))
        .order_by(FindingRow.created_at, FindingRow.label)
    )
    return [finding_view(row) for row in rows]


def route_to_specialists(state: IncidentState) -> list[Send] | list[str]:
    names = state.get("specialists", [])
    if not names:
        return [DIAGNOSE]
    focus = state.get("focus", {})
    return [
        Send(
            SPECIALIST,
            SpecialistTask(
                incident_id=state["incident_id"],
                specialist=name,
                focus=focus.get(name, []),
            ),
        )
        for name in names
    ]


class MultiNodes(IncidentNodes):
    async def plan(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            plan = await stored_plan(session, incident_id)
            if plan is None:
                plan = await create_plan(session, incident, self._runtime)
        available = [name for name in plan.specialists if name in self._runtime.specialists]
        return {
            "specialists": available,
            "focus": {name: plan.focus[name] for name in available if name in plan.focus},
        }

    async def specialist(self, state: IncidentState) -> Update:
        task = SPECIALIST_TASK.validate_python(state)
        incident_id = uuid.UUID(task["incident_id"])
        name = task["specialist"]
        agent = self._runtime.specialists[name]
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            if await succeeded_run_exists(session, incident_id, name):
                return {}
            prepared = await load_investigation_input(session, incident_id, name)
            run = new_agent_run(incident_id, name)
            session.add(run)
        run_id = run.id

        try:
            outcome = await agent.investigate(prepared.brief, task["focus"], prepared.context)
        except LLMError as exc:
            await self._fail_specialist(incident_id, run_id, name, exc)
            return {}

        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            agent_run = await session.get_one(AgentRun, run_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                mark_run_failed(agent_run, "incident left investigation before findings were saved")
                return {}
            finish_run(agent_run, outcome.stats)
            add_findings(session, incident_id, name, outcome.findings)
            await add_event(
                session,
                incident_id,
                FINISHED_EVENT,
                name,
                {"findings": len(outcome.findings), "dropped_findings": outcome.dropped_findings},
            )
        return {}

    async def diagnose(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            findings = await grounded_findings(session, incident_id)
            dropped = await dropped_specialist_findings(session, incident_id)
            if not findings:
                failure = await investigation_failure(session, incident_id)
                if failure is not None:
                    await transition(
                        session, incident, IncidentStatus.ESCALATED, DIAGNOSIS_AGENT, failure
                    )
                    return {"outcome": "escalated"}
                await persist_diagnosis(session, incident, unknown_diagnosis(NO_FINDINGS), dropped)
                await transition(session, incident, IncidentStatus.DIAGNOSED, DIAGNOSIS_AGENT)
                return {"outcome": "diagnosed"}
            prepared = await load_investigation_input(session, incident_id, DIAGNOSIS_AGENT)
            run = new_agent_run(incident_id, DIAGNOSIS_AGENT)
            session.add(run)
        run_id = run.id

        try:
            outcome = await self._runtime.diagnoser.diagnose(
                prepared.brief, findings, prepared.context
            )
        except LLMError as exc:
            await self._fail_investigation(incident_id, run_id, escalation_reason_for(exc), exc)
            return {"outcome": "escalated"}

        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            finish_run(await session.get_one(AgentRun, run_id), outcome.stats)
            await persist_diagnosis(session, incident, outcome.diagnosis, dropped)
            await transition(session, incident, IncidentStatus.DIAGNOSED, DIAGNOSIS_AGENT)
        return {"outcome": "diagnosed"}

    async def _fail_specialist(
        self, incident_id: uuid.UUID, run_id: uuid.UUID, name: str, error: Exception
    ) -> None:
        logger.warning("specialist_failed", specialist=name, error=str(error))
        async with transaction(self._sessions) as session:
            agent_run = await session.get_one(AgentRun, run_id)
            mark_run_failed(agent_run, f"{type(error).__name__}: {error}")
            await add_event(
                session, incident_id, FAILED_EVENT, name, {"error": type(error).__name__}
            )
