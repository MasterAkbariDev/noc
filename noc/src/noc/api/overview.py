import uuid
from collections.abc import Collection
from datetime import datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import ColumnElement

from noc.api.activity import activity_entry, is_uuid
from noc.api.deps import get_session, require_role
from noc.api.schemas import (
    ActivityItem,
    AttentionItem,
    ComponentHealth,
    FixedItem,
    FixKind,
    Kpis,
    LlmStatus,
    Overview,
    OverviewVerdict,
    ServerSummary,
    StoryAdvice,
    SystemHealth,
)
from noc.api.servers import load_server_summaries
from noc.api.story import approval_open, build_advice, build_headline
from noc.api.system import system_health
from noc.api.system_llm import get_llm_status
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import ActionRow, AuditEntry, Incident, IncidentEvent, Target
from noc.domain.incident_status import ACTIVE_STATUSES, OPEN_STATUSES, IncidentStatus
from noc.reporting import plain_language as words
from noc.reporting.event_text import resource_name
from noc.store.remediation import PENDING_APPROVAL, SUCCEEDED

router = APIRouter(
    prefix="/api/overview", tags=["overview"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]
REPLAY_MODE = "replay"
WORKING_KEY_STATES = frozenset({"ok", "unused"})
NEEDS_YOU_STATUSES = frozenset(
    {IncidentStatus.ESCALATED.value, IncidentStatus.AWAITING_APPROVAL.value}
)
PROBLEM_STATUSES = frozenset({"degraded", "down"})
ATTENTION_LIMIT = 20
ACTIVITY_LIMIT = 15
INCIDENT_CLOSED = "incident_closed"
NO_LLM_KEY_TEXT = "No AI model key is working"
CORE_DOWN_FALLBACK = "A core part is not answering"
DOWN_SENTENCE = "The NOC itself is not working right now"
DEGRADED_SENTENCE = "Something needs a look"
OK_SENTENCE = "Everything is running normally"
WORKING_DETAIL = "You do not need to do anything yet"
NO_SERVERS_SENTENCE = "No servers are watched yet"
NO_SERVERS_DETAIL = "Add one with noc targets add on the NOC server, and it appears here"
FIXED_WINDOW = timedelta(hours=24)
FIXED_SCAN_LIMIT = 200
FIXED_LIMIT = 8
APPROVAL_AUTHORIZATION_PREFIX = "approval:"
FIXED_SENTENCES: dict[FixKind, str] = {
    "automatic": "The NOC chose to {action} and did it on its own. The check afterwards passed.",
    "approved": "A person approved {action}. The NOC ran it and the check afterwards passed.",
    "by_itself": "The problem went away on its own before the NOC had to act.",
}


def key_is_working(state: str, mode: str) -> bool:
    return mode == REPLAY_MODE or state in WORKING_KEY_STATES


def llm_keys_working(status: LlmStatus) -> int:
    return sum(1 for key in status.keys if key_is_working(key.state, status.mode))


def count_phrase(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def needs_you_sentence(count: int) -> str:
    return "1 incident needs you" if count == 1 else f"{count} incidents need you"


def failing_summary(components: list[ComponentHealth], statuses: Collection[str]) -> str | None:
    component = next((item for item in components if item.status in statuses), None)
    return component.summary if component is not None else None


def server_problem(servers: list[ServerSummary]) -> str | None:
    for server in servers:
        if server.status == "down":
            return f"{server.name} is not reachable"
    for server in servers:
        if server.status == "unknown":
            return f"{server.name} status is unknown"
    for server in servers:
        if server.halted:
            return f"{server.name} is halted"
    return None


def degraded_problem(
    components: list[ComponentHealth], servers: list[ServerSummary], llm_ok: bool
) -> str | None:
    component = next((item for item in components if item.status in PROBLEM_STATUSES), None)
    if component is not None:
        return f"{component.label}: {component.summary}"
    problem = server_problem(servers)
    if problem is not None:
        return problem
    if not llm_ok:
        return NO_LLM_KEY_TEXT
    return None


def overview_verdict(
    health: SystemHealth,
    kpis: Kpis,
    active_incidents: int,
    servers: list[ServerSummary],
    llm_ok: bool,
) -> OverviewVerdict:
    if health.verdict == "down":
        reason = failing_summary(health.components, {"down"}) or CORE_DOWN_FALLBACK
        return OverviewVerdict(level="down", sentence=DOWN_SENTENCE, detail=reason)
    problem = degraded_problem(health.components, servers, llm_ok)
    if kpis.needs_you > 0:
        return OverviewVerdict(
            level="attention", sentence=needs_you_sentence(kpis.needs_you), detail=problem
        )
    if problem is not None:
        return OverviewVerdict(level="degraded", sentence=DEGRADED_SENTENCE, detail=problem)
    if active_incidents > 0:
        count = count_phrase(active_incidents, "incident", "incidents")
        return OverviewVerdict(
            level="working", sentence=f"The NOC is working on {count}", detail=WORKING_DETAIL
        )
    if kpis.servers_total == 0:
        return OverviewVerdict(level="ok", sentence=NO_SERVERS_SENTENCE, detail=NO_SERVERS_DETAIL)
    watched = count_phrase(kpis.servers_total, "server", "servers")
    return OverviewVerdict(level="ok", sentence=OK_SENTENCE, detail=f"Watching {watched}")


def attention_since(incident: Incident) -> datetime:
    return incident.escalated_at or incident.plan_at or incident.opened_at


def attention_since_column() -> ColumnElement[datetime]:
    return func.coalesce(Incident.escalated_at, Incident.plan_at, Incident.opened_at)


def attention_advice(status: IncidentStatus, advice: StoryAdvice) -> str:
    if status is IncidentStatus.AWAITING_APPROVAL or not advice.steps:
        return advice.text
    return advice.steps[0].text


def attention_item(
    incident: Incident, target_name: str, pending: ActionRow | None
) -> AttentionItem:
    status = IncidentStatus(incident.status)
    status_label = words.text_for(words.STATUS_LABELS, incident.status)
    advice = build_advice(incident, status, incident.root_cause_code, pending)
    return AttentionItem(
        incident_id=incident.id,
        title=incident.title,
        target=target_name,
        severity=incident.severity,
        status=incident.status,
        status_label=status_label,
        since=attention_since(incident),
        summary=build_headline(incident, status, status_label, pending),
        advice=attention_advice(status, advice),
    )


async def pending_actions(
    session: AsyncSession, incident_ids: list[uuid.UUID]
) -> dict[uuid.UUID, ActionRow]:
    if not incident_ids:
        return {}
    rows = await session.scalars(
        select(ActionRow).where(
            ActionRow.incident_id.in_(incident_ids), ActionRow.status == PENDING_APPROVAL
        )
    )
    return {row.incident_id: row for row in rows}


async def needs_attention(session: AsyncSession) -> list[AttentionItem]:
    rows = await session.execute(
        select(Incident, Target.name)
        .join(Target, Target.id == Incident.target_id)
        .where(Incident.status.in_(NEEDS_YOU_STATUSES))
        .order_by(attention_since_column(), Incident.id)
        .limit(ATTENTION_LIMIT)
    )
    waiting = rows.all()
    pending = await pending_actions(session, [incident.id for incident, _ in waiting])
    now = utc_now()
    return [
        attention_item(incident, target_name, open_pending(pending.get(incident.id), now))
        for incident, target_name in waiting
    ]


def open_pending(action: ActionRow | None, now: datetime) -> ActionRow | None:
    return action if action is not None and approval_open(action, now) else None


async def count_incidents(session: AsyncSession, statuses: Collection[str]) -> int:
    count = await session.scalar(
        select(func.count()).select_from(Incident).where(Incident.status.in_(list(statuses)))
    )
    return int(count or 0)


async def count_open_incidents(session: AsyncSession) -> int:
    return await count_incidents(session, [status.value for status in OPEN_STATUSES])


async def count_active_incidents(session: AsyncSession) -> int:
    return await count_incidents(session, [status.value for status in ACTIVE_STATUSES])


async def count_needs_you(session: AsyncSession) -> int:
    return await count_incidents(session, NEEDS_YOU_STATUSES)


def event_sentence(event: IncidentEvent, title: str) -> str:
    if event.type == words.STATE_CHANGED_EVENT:
        target_status = str(event.payload.get("to", ""))
        return f"{title}: {words.text_for(words.STATUS_LABELS, target_status)}"
    template = words.EVENT_SENTENCES.get(event.type)
    if template is None:
        return f"{title}: {words.humanize(event.type)}"
    return template.format(title=title, actor=event.actor)


def incident_activity(event: IncidentEvent, title: str) -> ActivityItem:
    return ActivityItem(
        ts=event.ts,
        kind="incident",
        text=event_sentence(event, title),
        incident_id=event.incident_id,
        actor=event.actor,
    )


def audit_incident_id(row: AuditEntry) -> uuid.UUID | None:
    if row.action == INCIDENT_CLOSED and is_uuid(row.subject):
        return uuid.UUID(row.subject)
    return None


def audit_activity(row: AuditEntry) -> ActivityItem:
    return ActivityItem(
        ts=row.ts,
        kind="audit",
        text=activity_entry(row).summary,
        incident_id=audit_incident_id(row),
        actor=row.actor,
    )


async def recent_activity(session: AsyncSession) -> list[ActivityItem]:
    event_rows = await session.execute(
        select(IncidentEvent, Incident.title)
        .join(Incident, Incident.id == IncidentEvent.incident_id)
        .order_by(IncidentEvent.ts.desc(), IncidentEvent.id.desc())
        .limit(ACTIVITY_LIMIT)
    )
    audit_rows = await session.scalars(
        select(AuditEntry)
        .order_by(AuditEntry.ts.desc(), AuditEntry.id.desc())
        .limit(ACTIVITY_LIMIT)
    )
    items = [incident_activity(event, title) for event, title in event_rows.all()]
    items.extend(audit_activity(row) for row in audit_rows)
    items.sort(key=lambda item: item.ts, reverse=True)
    return items[:ACTIVITY_LIMIT]


def fix_kind(incident: Incident, succeeded: list[ActionRow]) -> FixKind:
    if incident.status == IncidentStatus.SELF_RESOLVED.value or not succeeded:
        return "by_itself"
    approved = any(
        (action.authorization or "").startswith(APPROVAL_AUTHORIZATION_PREFIX)
        for action in succeeded
    )
    return "approved" if approved else "automatic"


def fixed_action_phrase(succeeded: list[ActionRow]) -> str:
    return ", ".join(
        f"{words.humanize(action.action_type).lower()} on {resource_name(action.resource_id)}"
        for action in succeeded
    )


def fixed_item(incident: Incident, target_name: str, succeeded: list[ActionRow]) -> FixedItem:
    kind = fix_kind(incident, succeeded)
    resolved_at = incident.resolved_at or incident.opened_at
    return FixedItem(
        incident_id=incident.id,
        title=incident.title,
        target=target_name,
        resolved_at=resolved_at,
        kind=kind,
        sentence=FIXED_SENTENCES[kind].format(action=fixed_action_phrase(succeeded)),
    )


async def succeeded_actions(
    session: AsyncSession, incident_ids: list[uuid.UUID]
) -> dict[uuid.UUID, list[ActionRow]]:
    found: dict[uuid.UUID, list[ActionRow]] = {}
    if not incident_ids:
        return found
    rows = await session.scalars(
        select(ActionRow)
        .where(ActionRow.incident_id.in_(incident_ids), ActionRow.status == SUCCEEDED)
        .order_by(ActionRow.created_at)
    )
    for row in rows:
        found.setdefault(row.incident_id, []).append(row)
    return found


async def recently_fixed(session: AsyncSession, now: datetime) -> list[FixedItem]:
    rows = await session.execute(
        select(Incident, Target.name)
        .join(Target, Target.id == Incident.target_id)
        .where(Incident.resolved_at.is_not(None), Incident.resolved_at >= now - FIXED_WINDOW)
        .order_by(Incident.resolved_at.desc(), Incident.id)
        .limit(FIXED_SCAN_LIMIT)
    )
    resolved = rows.all()
    actions = await succeeded_actions(session, [incident.id for incident, _ in resolved])
    return [
        fixed_item(incident, target_name, actions.get(incident.id, []))
        for incident, target_name in resolved
    ]


@router.get("")
async def get_overview(request: Request, session: Session) -> Overview:
    settings: Settings = request.app.state.settings
    health = await system_health(request, session)
    llm = await get_llm_status(session, settings)
    servers = await load_server_summaries(session, request.app.state.prometheus)
    attention = await needs_attention(session)
    working_keys = llm_keys_working(llm)
    fixed = await recently_fixed(session, utc_now())
    kpis = Kpis(
        open_incidents=await count_open_incidents(session),
        needs_you=await count_needs_you(session),
        servers_up=sum(1 for server in servers if server.status == "up"),
        servers_total=len(servers),
        llm_keys_ok=working_keys,
        llm_keys_total=len(llm.keys),
        fixed_today=len(fixed),
        fixed_automatically_today=sum(1 for item in fixed if item.kind == "automatic"),
    )
    llm_ok = llm.mode == REPLAY_MODE or working_keys > 0
    active = await count_active_incidents(session)
    return Overview(
        verdict=overview_verdict(health, kpis, active, servers, llm_ok),
        kpis=kpis,
        needs_attention=attention,
        fixed=fixed[:FIXED_LIMIT],
        activity=await recent_activity(session),
        servers=servers,
    )
