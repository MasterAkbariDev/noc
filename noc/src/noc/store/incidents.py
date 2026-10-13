import uuid
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import Incident, IncidentEvent
from noc.domain.incident_status import (
    OPEN_STATUSES,
    TIMESTAMP_FIELD,
    EscalationReason,
    IncidentStatus,
    ensure_transition,
)

EVENTS_CHANNEL = "incident_events"


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


async def find_open_incident(session: AsyncSession, target_id: uuid.UUID) -> Incident | None:
    open_values = [status.value for status in OPEN_STATUSES]
    return await session.scalar(
        select(Incident).where(Incident.target_id == target_id, Incident.status.in_(open_values))
    )
