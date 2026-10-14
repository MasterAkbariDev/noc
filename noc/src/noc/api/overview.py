import uuid
from collections.abc import Collection
from datetime import datetime
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
    Kpis,
    LlmStatus,
    Overview,
    OverviewVerdict,
    ServerSummary,
    StoryAdvice,
    SystemHealth,
)
from noc.api.servers import load_server_summaries
from noc.api.story import build_advice, build_headline
from noc.api.system import system_health
from noc.api.system_llm import get_llm_status
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.models import ActionRow, AuditEntry, Incident, IncidentEvent, Target
from noc.domain.incident_status import ACTIVE_STATUSES, OPEN_STATUSES, IncidentStatus
from noc.reporting import plain_language as words
from noc.store.remediation import PENDING_APPROVAL

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
CORE_DOWN_FALLBACK = "a core part is not answering"
LLM_OK_TEXT = "LLM OK"
SENTENCE_SEPARATOR = " · "


def key_is_working(state: str, mode: str) -> bool:
    return mode == REPLAY_MODE or state in WORKING_KEY_STATES


def llm_keys_working(status: LlmStatus) -> int:
    return sum(1 for key in status.keys if key_is_working(key.state, status.mode))


def count_phrase(count: int, singular: str, plural: str) -> str:
    return f"{count} {singular if count == 1 else plural}"


def needs_you_sentence(count: int) -> str:
    return "1 incident needs you" if count == 1 else f"{count} incidents need you"


def joined(*parts: str | None) -> str:
    return SENTENCE_SEPARATOR.join(part for part in parts if part is not None)


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
        return OverviewVerdict(level="down", sentence=f"The NOC is not working: {reason}")
    problem = degraded_problem(health.components, servers, llm_ok)
    if kpis.needs_you > 0:
        sentence = joined(needs_you_sentence(kpis.needs_you), problem)
        return OverviewVerdict(level="attention", sentence=sentence)
    if problem is not None:
        return OverviewVerdict(level="degraded", sentence=problem)
    if active_incidents > 0:
        sentence = joined(
            f"Working on {count_phrase(active_incidents, 'incident', 'incidents')}",
            f"{count_phrase(kpis.servers_up, 'server', 'servers')} up",
            LLM_OK_TEXT,
        )
        return OverviewVerdict(level="working", sentence=sentence)
    sentence = joined(
        count_phrase(kpis.servers_total, "server", "servers"),
        count_phrase(kpis.open_incidents, "open incident", "open incidents"),
        LLM_OK_TEXT,
    )
    return OverviewVerdict(level="ok", sentence=sentence)


def attention_since(incident: Incident) -> datetime:
    return incident.escalated_at or incident.plan_at or incident.opened_at


def attention_since_column() -> ColumnElement[datetime]:
    return func.coalesce(Incident.escalated_at, Incident.plan_at, Incident.opened_at)


def attention_advice(status: IncidentStatus, advice: StoryAdvice) -> str:
    if status is IncidentStatus.AWAITING_APPROVAL or not advice.steps:
        return advice.text
    return advice.steps[0]


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
        summary=build_headline(incident, status, status_label),
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
    return [
        attention_item(incident, target_name, pending.get(incident.id))
        for incident, target_name in waiting
    ]


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


@router.get("")
async def get_overview(request: Request, session: Session) -> Overview:
    settings: Settings = request.app.state.settings
    health = await system_health(request, session)
    llm = await get_llm_status(session, settings)
    servers = await load_server_summaries(session, request.app.state.prometheus)
    attention = await needs_attention(session)
    working_keys = llm_keys_working(llm)
    kpis = Kpis(
        open_incidents=await count_open_incidents(session),
        needs_you=await count_needs_you(session),
        servers_up=sum(1 for server in servers if server.status == "up"),
        servers_total=len(servers),
        llm_keys_ok=working_keys,
        llm_keys_total=len(llm.keys),
    )
    llm_ok = llm.mode == REPLAY_MODE or working_keys > 0
    active = await count_active_incidents(session)
    return Overview(
        verdict=overview_verdict(health, kpis, active, servers, llm_ok),
        kpis=kpis,
        needs_attention=attention,
        activity=await recent_activity(session),
        servers=servers,
    )
