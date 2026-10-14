import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_role
from noc.api.schemas import ActivityEntry, ActivityPage, ChainVerification
from noc.audit.chain import verify_chain
from noc.auth.roles import Role
from noc.db.models import AuditEntry
from noc.reporting import plain_language as words

router = APIRouter(
    prefix="/api/activity", tags=["activity"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=200)]
DEFAULT_LIMIT = 50
USER_SUBJECT_PREFIX = "user:"
SHORT_ID_LENGTH = 8

SENTENCES: dict[str, str] = {
    "user_created": "{actor} created the user {subject}",
    "user_disabled": "{actor} disabled the user {subject}",
    "user_enabled": "{actor} enabled the user {subject}",
    "user_role_changed": "{actor} changed the role of {subject}",
    "user_password_reset": "{actor} reset the password of {subject}",
    "password_changed": "{actor} changed their password",
    "login": "{actor} signed in",
    "logout": "{actor} signed out",
    "login_failed": "Failed sign-in for {subject}",
    "incident_closed": "{actor} closed incident {subject}",
    "target_added": "{actor} added the target {subject}",
    "target_automation_set": "{actor} changed the automation level of {subject}",
    "target_auto_actions_set": "{actor} changed the automatic actions of {subject}",
    "target_profile_set": "{actor} changed the service profile of {subject}",
    "scenario_run_started": "{actor} started the chaos scenario {subject}",
    "scenario_run_finished": "The chaos scenario {subject} finished",
}


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


def shown_subject(subject: str) -> str:
    if subject.startswith(USER_SUBJECT_PREFIX):
        return subject.removeprefix(USER_SUBJECT_PREFIX)
    if is_uuid(subject):
        return f"{subject[:SHORT_ID_LENGTH]}…"
    return subject


def summarize(action: str, actor: str, subject: str) -> str:
    shown = shown_subject(subject)
    template = SENTENCES.get(action)
    if template is None:
        label = words.text_for(words.AUDIT_ACTION_LABELS, action)
        return f"{label} by {actor}: {shown}"
    return template.format(actor=actor, subject=shown)


def activity_entry(row: AuditEntry) -> ActivityEntry:
    return ActivityEntry(
        id=row.id,
        ts=row.ts,
        actor=row.actor,
        action=row.action,
        action_label=words.text_for(words.AUDIT_ACTION_LABELS, row.action),
        subject=row.subject,
        summary=summarize(row.action, row.actor, row.subject),
        payload=row.payload,
    )


@router.get("")
async def list_activity(
    session: Session,
    limit: Limit = DEFAULT_LIMIT,
    before_id: int | None = None,
    action: str | None = None,
    actor: str | None = None,
) -> ActivityPage:
    query = select(AuditEntry).order_by(AuditEntry.id.desc()).limit(limit + 1)
    if before_id is not None:
        query = query.where(AuditEntry.id < before_id)
    if action:
        query = query.where(AuditEntry.action == action)
    if actor:
        query = query.where(AuditEntry.actor == actor)
    rows = list(await session.scalars(query))
    page = rows[:limit]
    has_more = len(rows) > limit
    return ActivityPage(
        items=[activity_entry(row) for row in page],
        next_before_id=page[-1].id if has_more else None,
    )


@router.get("/verify")
async def verify_activity(session: Session) -> ChainVerification:
    broken_at = await verify_chain(session)
    return ChainVerification(ok=broken_at is None, broken_at=broken_at)
