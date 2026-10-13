import uuid
from dataclasses import dataclass

import structlog
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import AlertEvent, Incident, Target
from noc.domain.incident_status import IncidentStatus
from noc.domain.severity import Severity
from noc.jobs.queue import enqueue
from noc.store.incidents import add_event, find_active_incident

logger = structlog.get_logger(__name__)

INVESTIGATE_JOB = "investigate"


@dataclass(frozen=True)
class Correlation:
    incident_id: uuid.UUID
    created: bool


def investigate_dedupe_key(incident_id: uuid.UUID) -> str:
    return f"{INVESTIGATE_JOB}:{incident_id}"


def incident_title(alert: AlertEvent, target: Target) -> str:
    resource = alert.labels.get("resource")
    subject = f"{target.name}/{resource}" if resource else target.name
    return f"{alert.alertname} on {subject}"


async def lock_target(session: AsyncSession, target_id: uuid.UUID) -> None:
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtext(:key))"), {"key": f"target:{target_id}"}
    )


async def correlate(session: AsyncSession, alert: AlertEvent) -> Correlation | None:
    target_name = alert.labels.get("target")
    target = await session.scalar(select(Target).where(Target.name == target_name))
    if target is None:
        logger.warning("alert_without_registered_target", alertname=alert.alertname)
        return None

    alert.target_id = target.id
    severity = Severity.parse(alert.severity)
    if severity is Severity.INFO:
        return None

    await lock_target(session, target.id)
    incident = await find_active_incident(session, target.id)
    if incident is not None:
        alert.incident_id = incident.id
        incident.severity = Severity.highest(Severity.parse(incident.severity), severity).value
        await add_event(session, incident.id, "alert_attached", "correlator", alert_payload(alert))
        return Correlation(incident.id, created=False)

    incident = Incident(
        target_id=target.id,
        status=IncidentStatus.NEW.value,
        severity=severity.value,
        title=incident_title(alert, target),
        trace_id=uuid.uuid4().hex,
    )
    session.add(incident)
    await session.flush()
    alert.incident_id = incident.id
    await add_event(session, incident.id, "incident_opened", "correlator", alert_payload(alert))
    await enqueue(
        session,
        kind=INVESTIGATE_JOB,
        payload={"incident_id": str(incident.id)},
        dedupe_key=investigate_dedupe_key(incident.id),
        priority=severity.rank,
    )
    return Correlation(incident.id, created=True)


def alert_payload(alert: AlertEvent) -> dict[str, object]:
    return {"alertname": alert.alertname, "fingerprint": alert.fingerprint, "value": alert.value}
