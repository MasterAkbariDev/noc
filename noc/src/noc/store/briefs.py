import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from noc.agents.brief import AlertBrief, IncidentBrief, ResourceBrief
from noc.db.models import AlertEvent, Incident, Target
from noc.tools.spec import TargetRef, ToolContext


@dataclass(frozen=True)
class InvestigationInput:
    brief: IncidentBrief
    context: ToolContext


def target_ref(target: Target) -> TargetRef:
    return TargetRef(
        id=target.id,
        name=target.name,
        sentinel_url=target.sentinel_url,
        hmac_key_id=target.hmac_key_id,
        environment=target.environment,
        data_policy=target.llm_data_policy,
    )


async def load_investigation_input(
    session: AsyncSession, incident_id: uuid.UUID, agent: str
) -> InvestigationInput:
    incident = await session.scalar(
        select(Incident)
        .where(Incident.id == incident_id)
        .options(selectinload(Incident.target).selectinload(Target.resources))
    )
    if incident is None:
        raise LookupError(f"incident {incident_id} not found")
    alerts = await session.scalars(
        select(AlertEvent)
        .where(AlertEvent.incident_id == incident_id)
        .order_by(AlertEvent.starts_at)
    )
    target = incident.target
    brief = IncidentBrief(
        title=incident.title,
        target=target.name,
        environment=target.environment,
        alerts=[
            AlertBrief(
                alertname=alert.alertname,
                severity=alert.severity,
                resource=alert.labels.get("resource"),
                value=alert.value,
                firing_since=alert.starts_at,
                summary=alert.annotations.get("summary"),
            )
            for alert in alerts
        ],
        resources=[
            ResourceBrief(id=resource.resource_id, kind=resource.kind, name=resource.name)
            for resource in target.resources
        ],
    )
    context = ToolContext(
        incident_id=incident.id, agent=agent, target=target_ref(target), trace_id=incident.trace_id
    )
    return InvestigationInput(brief=brief, context=context)


async def all_alerts_resolved(session: AsyncSession, incident_id: uuid.UUID) -> bool:
    firing = await session.scalar(
        select(AlertEvent.id)
        .where(AlertEvent.incident_id == incident_id, AlertEvent.state == "firing")
        .limit(1)
    )
    return firing is None
