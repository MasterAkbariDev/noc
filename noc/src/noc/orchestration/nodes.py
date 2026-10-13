import uuid
from typing import Any

import structlog
from sqlalchemy import select

from noc.db.base import utc_now
from noc.db.models import ActionRow, AgentRun, AlertEvent, DiagnosisRow, Incident, Report
from noc.db.session import transaction
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.llm.client import LLMError, LLMUnavailable, describe_error
from noc.orchestration.runtime import Runtime
from noc.orchestration.state import IncidentState
from noc.reporting.builder import load_report_data, render_report
from noc.store.briefs import all_alerts_resolved, load_investigation_input
from noc.store.decisions import decide_actions, decisions_exist
from noc.store.incidents import add_event, lock_incident, transition
from noc.store.investigations import new_agent_run, save_investigation

logger = structlog.get_logger(__name__)

MIN_ACTIONABLE_CONFIDENCE = 0.6
SUPERVISOR = "supervisor"
POLICY = "policy"
REPORTER = "reporter"

Update = dict[str, Any]


def incident_id_of(state: IncidentState) -> uuid.UUID:
    return uuid.UUID(state["incident_id"])


def affected_resource(diagnosis: DiagnosisRow, alerts: list[AlertEvent]) -> str | None:
    primary = max(diagnosis.hypotheses, key=lambda hypothesis: hypothesis["confidence"])
    from_diagnosis = primary.get("affected_resource_id")
    if from_diagnosis:
        return str(from_diagnosis)
    return next((alert.labels["resource"] for alert in alerts if "resource" in alert.labels), None)


def escalation_reason_for(error: LLMError) -> EscalationReason:
    return (
        EscalationReason.LLM_UNAVAILABLE
        if isinstance(error, LLMUnavailable)
        else EscalationReason.INVESTIGATION_FAILED
    )


class IncidentNodes:
    def __init__(self, runtime: Runtime) -> None:
        self._runtime = runtime
        self._sessions = runtime.sessions

    async def begin(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.NEW:
                return {}
            await transition(session, incident, IncidentStatus.INVESTIGATING, SUPERVISOR)
            if await all_alerts_resolved(session, incident_id):
                await transition(session, incident, IncidentStatus.SELF_RESOLVED, SUPERVISOR)
                return {"outcome": "self_resolved"}
        return {}

    async def investigate(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        investigator = self._runtime.investigator
        async with transaction(self._sessions) as session:
            incident = await session.get_one(Incident, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            prepared = await load_investigation_input(session, incident_id, investigator.name)
            agent_run = new_agent_run(incident_id, investigator.name)
            session.add(agent_run)

        try:
            outcome = await investigator.investigate(prepared.brief, prepared.context)
        except LLMError as exc:
            await self._fail_investigation(
                incident_id, agent_run.id, escalation_reason_for(exc), exc
            )
            return {"outcome": "escalated"}

        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.INVESTIGATING:
                return {}
            run = await session.merge(agent_run)
            await save_investigation(session, incident, investigator.name, run, outcome)
            await transition(session, incident, IncidentStatus.DIAGNOSED, investigator.name)
        return {"outcome": "diagnosed"}

    async def _fail_investigation(
        self,
        incident_id: uuid.UUID,
        agent_run_id: uuid.UUID,
        reason: EscalationReason,
        error: Exception,
    ) -> None:
        logger.warning("investigation_failed", incident_id=str(incident_id), error=str(error))
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            run = await session.get_one(AgentRun, agent_run_id)
            run.status = "failed"
            run.ended_at = utc_now()
            run.error = describe_error(error)
            if IncidentStatus(incident.status) is IncidentStatus.INVESTIGATING:
                await transition(session, incident, IncidentStatus.ESCALATED, SUPERVISOR, reason)

    async def decide(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        settings = self._runtime.settings
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            if IncidentStatus(incident.status) is not IncidentStatus.DIAGNOSED:
                return {}
            diagnosis = await session.scalar(
                select(DiagnosisRow)
                .where(DiagnosisRow.incident_id == incident_id)
                .order_by(DiagnosisRow.created_at.desc())
                .limit(1)
            )
            if diagnosis is None or diagnosis.primary_code == "unknown":
                await transition(
                    session,
                    incident,
                    IncidentStatus.ESCALATED,
                    POLICY,
                    EscalationReason.UNKNOWN_ROOT_CAUSE,
                )
                return {"outcome": "escalated"}
            if diagnosis.confidence < MIN_ACTIONABLE_CONFIDENCE:
                await transition(
                    session,
                    incident,
                    IncidentStatus.ESCALATED,
                    POLICY,
                    EscalationReason.LOW_CONFIDENCE,
                )
                return {"outcome": "escalated"}

            alerts = list(
                await session.scalars(
                    select(AlertEvent).where(AlertEvent.incident_id == incident_id)
                )
            )
            if not await decisions_exist(session, incident_id):
                await decide_actions(
                    session,
                    incident,
                    diagnosis,
                    affected_resource(diagnosis, alerts),
                    self._runtime.policy,
                    settings.execution_enabled,
                    settings.automation_paused,
                )
            await transition(session, incident, IncidentStatus.PLANNED, POLICY)
            eligible = await session.scalar(
                select(ActionRow.id)
                .where(ActionRow.incident_id == incident_id, ActionRow.eligible.is_(True))
                .limit(1)
            )
            reason = (
                EscalationReason.EXECUTION_NOT_AVAILABLE
                if eligible is not None
                else EscalationReason.NO_ALLOWED_ACTION
            )
            await transition(session, incident, IncidentStatus.ESCALATED, POLICY, reason)
        return {"outcome": "escalated"}

    async def report(self, state: IncidentState) -> Update:
        incident_id = incident_id_of(state)
        async with transaction(self._sessions) as session:
            incident = await lock_incident(session, incident_id)
            existing = await session.scalar(
                select(Report.id).where(Report.incident_id == incident_id)
            )
            if existing is None:
                markdown = render_report(await load_report_data(session, incident_id))
                session.add(Report(incident_id=incident_id, markdown=markdown))
                await add_event(session, incident_id, "report_generated", REPORTER)
            if IncidentStatus(incident.status) is IncidentStatus.SELF_RESOLVED:
                await transition(session, incident, IncidentStatus.CLOSED, REPORTER)
        return {}


def route_after_begin(state: IncidentState) -> str:
    return "report" if state.get("outcome") == "self_resolved" else "investigate"
