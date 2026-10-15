import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import PlainTextResponse
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from noc.api.deps import Principal, get_session, get_settings_dep, require_role
from noc.api.schemas import (
    ActionView,
    ApprovalRequest,
    ApprovalView,
    DiagnosisView,
    EventView,
    FindingView,
    HypothesisView,
    IncidentDetail,
    IncidentSummary,
)
from noc.auth.approval_factor import SecondFactorRefused, confirm_second_factor
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.models import (
    ActionRow,
    DiagnosisRow,
    FindingRow,
    Incident,
    IncidentEvent,
    Report,
    Target,
)
from noc.domain.incident_status import InvalidTransition
from noc.policy.models import Environment
from noc.store.incidents import IncidentResolution, close_incident
from noc.store.remediation import ApprovalConflict, record_approval

router = APIRouter(
    prefix="/api/incidents", tags=["incidents"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]
OperatorPrincipal = Annotated[Principal, Depends(require_role(Role.OPERATOR))]
AppSettings = Annotated[Settings, Depends(get_settings_dep)]

MAX_SEARCH_LENGTH = 100
LIKE_ESCAPE = "\\"


def summarize(incident: Incident, target_name: str) -> IncidentSummary:
    return IncidentSummary(
        id=incident.id,
        title=incident.title,
        status=incident.status,
        severity=incident.severity,
        target=target_name,
        opened_at=incident.opened_at,
        root_cause_code=incident.root_cause_code,
        confidence=incident.confidence,
        escalation_reason=incident.escalation_reason,
    )


def diagnosis_view(diagnosis: DiagnosisRow | None) -> DiagnosisView | None:
    if diagnosis is None:
        return None
    return DiagnosisView(
        primary_code=diagnosis.primary_code,
        confidence=diagnosis.confidence,
        is_security_incident=diagnosis.is_security_incident,
        hypotheses=[HypothesisView.model_validate(item) for item in diagnosis.hypotheses],
        needs_more_info=diagnosis.needs_more_info,
        ungrounded_findings=diagnosis.ungrounded_findings,
    )


def contains_pattern(text: str) -> str:
    escaped = (
        text.replace(LIKE_ESCAPE, LIKE_ESCAPE * 2)
        .replace("%", f"{LIKE_ESCAPE}%")
        .replace("_", f"{LIKE_ESCAPE}_")
    )
    return f"%{escaped}%"


@router.get("")
async def list_incidents(
    session: Session,
    status: str | None = None,
    statuses: Annotated[list[str] | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=MAX_SEARCH_LENGTH)] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> list[IncidentSummary]:
    query = (
        select(Incident)
        .options(selectinload(Incident.target))
        .order_by(Incident.opened_at.desc())
        .limit(limit)
    )
    if status:
        query = query.where(Incident.status == status.upper())
    if statuses:
        query = query.where(Incident.status.in_([value.upper() for value in statuses]))
    needle = (q or "").strip()
    if needle:
        pattern = contains_pattern(needle)
        query = query.join(Incident.target).where(
            or_(
                Incident.title.ilike(pattern, escape=LIKE_ESCAPE),
                Target.name.ilike(pattern, escape=LIKE_ESCAPE),
            )
        )
    return [summarize(row, row.target.name) for row in await session.scalars(query)]


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
    diagnosis = await session.scalar(
        select(DiagnosisRow)
        .where(DiagnosisRow.incident_id == incident_id)
        .order_by(DiagnosisRow.created_at.desc())
        .limit(1)
    )
    summary = summarize(incident, target.name)
    return IncidentDetail(
        **summary.model_dump(),
        mode=incident.mode,
        root_cause_summary=incident.root_cause_summary,
        resolution_note=incident.resolution_note,
        investigation_started_at=incident.investigation_started_at,
        diagnosed_at=incident.diagnosed_at,
        plan_at=incident.plan_at,
        escalated_at=incident.escalated_at,
        resolved_at=incident.resolved_at,
        closed_at=incident.closed_at,
        trace_id=incident.trace_id,
        events=[EventView.model_validate(event) for event in events],
        findings=[FindingView.model_validate(finding) for finding in findings],
        actions=[ActionView.model_validate(action) for action in actions],
        report_markdown=report,
        diagnosis=diagnosis_view(diagnosis),
    )


@router.get("/{incident_id}/report", response_class=PlainTextResponse)
async def get_report(incident_id: uuid.UUID, session: Session) -> str:
    report = await session.scalar(select(Report.markdown).where(Report.incident_id == incident_id))
    if report is None:
        raise HTTPException(404, "report not ready")
    return report


@router.post("/{incident_id}/close")
async def close_escalated_incident(
    incident_id: uuid.UUID,
    resolution: IncidentResolution,
    session: Session,
    operator: OperatorPrincipal,
) -> IncidentSummary:
    try:
        incident = await close_incident(session, incident_id, resolution, operator.username)
    except LookupError as error:
        raise HTTPException(404, "incident not found") from error
    except InvalidTransition as error:
        raise HTTPException(409, str(error)) from error
    target = await session.get_one(Target, incident.target_id)
    await session.commit()
    return summarize(incident, target.name)


async def require_fresh_code(
    session: AsyncSession, incident_id: uuid.UUID, operator: Principal, code: str | None
) -> None:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    target = await session.get_one(Target, incident.target_id)
    if target.environment != Environment.PROD.value:
        return
    try:
        await confirm_second_factor(session, operator.user_id, code, f"incident:{incident_id}")
    except SecondFactorRefused as error:
        raise HTTPException(403, str(error)) from error


@router.post("/{incident_id}/actions/{action_id}/decision")
async def decide_on_action(
    incident_id: uuid.UUID,
    action_id: uuid.UUID,
    request: ApprovalRequest,
    session: Session,
    operator: OperatorPrincipal,
    settings: AppSettings,
) -> ApprovalView:
    if request.decision == "approved" and settings.prod_approval_requires_totp:
        await require_fresh_code(session, incident_id, operator, request.totp)
    try:
        recorded = await record_approval(
            session,
            incident_id,
            action_id,
            request.decision,
            operator.username,
            request.action_hash,
            request.comment,
        )
    except LookupError as error:
        raise HTTPException(404, "incident not found") from error
    except ApprovalConflict as error:
        raise HTTPException(409, str(error)) from error
    await session.commit()
    return ApprovalView(
        approval_id=recorded.approval_id, incident_status=recorded.incident_status.value
    )
