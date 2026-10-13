import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_token
from noc.api.schemas import ActionView, EventView, FindingView, IncidentDetail, IncidentSummary
from noc.db.models import ActionRow, FindingRow, Incident, IncidentEvent, Report, Target

router = APIRouter(
    prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(require_token)]
)

Session = Annotated[AsyncSession, Depends(get_session)]


@router.get("")
async def list_incidents(
    session: Session,
    status: str | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IncidentSummary]:
    query = select(Incident).order_by(Incident.opened_at.desc()).limit(limit)
    if status:
        query = query.where(Incident.status == status.upper())
    return [IncidentSummary.model_validate(row) for row in await session.scalars(query)]


@router.get("/{incident_id}")
async def get_incident(incident_id: uuid.UUID, session: Session) -> IncidentDetail:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    target = await session.get_one(Target, incident.target_id)
    events = await session.scalars(
        select(IncidentEvent)
        .where(IncidentEvent.incident_id == incident_id)
        .order_by(IncidentEvent.id)
    )
    findings = await session.scalars(
        select(FindingRow).where(FindingRow.incident_id == incident_id).order_by(FindingRow.label)
    )
    actions = await session.scalars(select(ActionRow).where(ActionRow.incident_id == incident_id))
    report = await session.scalar(select(Report.markdown).where(Report.incident_id == incident_id))
    summary = IncidentSummary.model_validate(incident)
    return IncidentDetail(
        **summary.model_dump(),
        target=target.name,
        trace_id=incident.trace_id,
        events=[EventView.model_validate(event) for event in events],
        findings=[FindingView.model_validate(finding) for finding in findings],
        actions=[ActionView.model_validate(action) for action in actions],
        report_markdown=report,
    )


@router.get("/{incident_id}/report", response_class=PlainTextResponse)
async def get_report(incident_id: uuid.UUID, session: Session) -> str:
    report = await session.scalar(select(Report.markdown).where(Report.incident_id == incident_id))
    if report is None:
        raise HTTPException(404, "report not ready")
    return report
