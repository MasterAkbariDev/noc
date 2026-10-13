import uuid
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from noc.audit.chain import append_audit
from noc.db.base import utc_now
from noc.db.models import AgentRun, Incident, IncidentEvent
from noc.domain.incident_status import (
    ACTIVE_STATUSES,
    CLOSED_STATUSES,
    TIMESTAMP_FIELD,
    EscalationReason,
    IncidentStatus,
    InvalidTransition,
    ensure_transition,
)
from noc_shared.taxonomy import RootCauseCode

EVENTS_CHANNEL = "incident_events"


class IncidentResolution(BaseModel):
    resolution_note: str = Field(min_length=1, max_length=2000)
    corrected_root_cause_code: RootCauseCode | None = None


async def add_event(
    session: AsyncSession,
    incident_id: uuid.UUID,
    event_type: str,
    actor: str,
    payload: dict[str, Any] | None = None,
) -> IncidentEvent:
    event = IncidentEvent(
        incident_id=incident_id, type=event_type, actor=actor, payload=payload or {}
    )
    session.add(event)
    await session.flush()
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": EVENTS_CHANNEL, "payload": f"{incident_id}:{event.id}"},
    )
    return event


async def transition(
    session: AsyncSession,
    incident: Incident,
    requested: IncidentStatus,
    actor: str,
    reason: EscalationReason | None = None,
) -> None:
    current = IncidentStatus(incident.status)
    ensure_transition(current, requested)
    incident.status = requested.value
    field = TIMESTAMP_FIELD.get(requested)
    if field is not None:
        setattr(incident, field, utc_now())
    if reason is not None:
        incident.escalation_reason = reason.value
    payload = {"from": current.value, "to": requested.value, "reason": reason}
    await add_event(session, incident.id, "state_changed", actor, payload)


async def lock_incident(session: AsyncSession, incident_id: uuid.UUID) -> Incident:
    incident = await session.scalar(
        select(Incident).where(Incident.id == incident_id).with_for_update()
    )
    if incident is None:
        raise LookupError(f"incident {incident_id} not found")
    return incident


async def close_incident(
    session: AsyncSession,
    incident_id: uuid.UUID,
    resolution: IncidentResolution,
    actor: str,
) -> Incident:
    incident = await lock_incident(session, incident_id)
    current = IncidentStatus(incident.status)
    if current is not IncidentStatus.ESCALATED:
        raise InvalidTransition(current, IncidentStatus.CLOSED)
    await transition(session, incident, IncidentStatus.CLOSED, actor)
    incident.resolution_note = resolution.resolution_note
    code = resolution.corrected_root_cause_code
    incident.corrected_root_cause_code = code.value if code is not None else None
    await append_audit(
        session,
        actor,
        "incident_closed",
        str(incident.id),
        {"corrected_root_cause_code": incident.corrected_root_cause_code},
    )
    return incident


async def find_active_incident(session: AsyncSession, target_id: uuid.UUID) -> Incident | None:
    active_values = [status.value for status in ACTIVE_STATUSES]
    return await session.scalar(
        select(Incident).where(Incident.target_id == target_id, Incident.status.in_(active_values))
    )


ABANDONED_RUN_ERROR = "abandoned: the investigation job gave up"
ABANDON_ACTOR = "worker"


async def escalate_abandoned(
    session: AsyncSession, incident_id: uuid.UUID, reason: EscalationReason, detail: str
) -> bool:
    incident = await lock_incident(session, incident_id)
    current = IncidentStatus(incident.status)
    if current in CLOSED_STATUSES or current is IncidentStatus.ESCALATED:
        return False
    await session.execute(
        update(AgentRun)
        .where(AgentRun.incident_id == incident_id, AgentRun.status == "running")
        .values(status="failed", ended_at=utc_now(), error=ABANDONED_RUN_ERROR)
    )
    if current is IncidentStatus.NEW:
        await transition(session, incident, IncidentStatus.INVESTIGATING, ABANDON_ACTOR)
    await transition(session, incident, IncidentStatus.ESCALATED, ABANDON_ACTOR, reason)
    await add_event(
        session, incident_id, "investigation_abandoned", ABANDON_ACTOR, {"error": detail}
    )
    return True
