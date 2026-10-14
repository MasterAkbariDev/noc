import uuid
from collections.abc import Collection
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.activity import activity_entry, is_uuid
from noc.api.deps import get_session, require_role
from noc.api.schemas import (
    ActivityItem,
    AttentionItem,
    ComponentHealth,
    IncidentStory,
    Kpis,
    LlmStatus,
    Overview,
    OverviewVerdict,
    ServerSummary,
    StoryAdvice,
    SystemHealth,
)
from noc.api.servers import load_server_summaries
from noc.api.story import get_incident_story
from noc.api.system import system_health
from noc.api.system_llm import get_llm_status
from noc.auth.roles import Role
from noc.config import Settings
from noc.db.models import AuditEntry, Incident, IncidentEvent, Target
from noc.domain.incident_status import OPEN_STATUSES, IncidentStatus
from noc.reporting import plain_language as words

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
ACTIVITY_LIMIT = 15
INCIDENT_CLOSED = "incident_closed"
STATE_CHANGED = "state_changed"
ALL_OK_TEXT = "All systems operational"
NO_LLM_KEY_TEXT = "No AI model key is working"
CORE_DOWN_FALLBACK = "a core part is not answering"
EVENT_SENTENCES: dict[str, str] = {
    "incident_opened": "{title} was opened",
    "alert_attached": "An alert was added to {title}",
    "report_generated": "A report was written for {title}",
    "investigation_planned": "The investigation of {title} was planned",
    "investigation_abandoned": "The investigation of {title} was abandoned",
    "specialist_unavailable": "A specialist was unavailable for {title}",
    "specialist_finished": "{actor} finished checking {title}",
    "specialist_failed": "{actor} failed while checking {title}",
}


def key_is_working(state: str, mode: str) -> bool:
    return mode == REPLAY_MODE or state in WORKING_KEY_STATES


def llm_keys_working(status: LlmStatus) -> int:
    return sum(1 for key in status.keys if key_is_working(key.state, status.mode))


def needs_you_sentence(count: int) -> str:
    return "1 incident needs you" if count == 1 else f"{count} incidents need you"


def failing_summary(components: list[ComponentHealth], statuses: Collection[str]) -> str | None:
    component = next((item for item in components if item.status in statuses), None)
    return component.summary if component is not None else None


def degraded_problem(
    components: list[ComponentHealth], servers: list[ServerSummary], llm_ok: bool
) -> str | None:
    component = next((item for item in components if item.status in PROBLEM_STATUSES), None)
    if component is not None:
        return f"{component.label}: {component.summary}"
    server = next((item for item in servers if item.status == "down"), None)
    if server is not None:
        return f"{server.name} is not reachable"
    if not llm_ok:
        return NO_LLM_KEY_TEXT
    return None


def overview_verdict(
    health: SystemHealth, needs_you: int, servers: list[ServerSummary], llm_ok: bool
) -> OverviewVerdict:
    if health.verdict == "down":
        reason = failing_summary(health.components, {"down"}) or CORE_DOWN_FALLBACK
        return OverviewVerdict(level="down", sentence=f"The NOC is not working: {reason}")
    if needs_you > 0:
        return OverviewVerdict(level="attention", sentence=needs_you_sentence(needs_you))
    problem = degraded_problem(health.components, servers, llm_ok)
    if problem is not None:
        return OverviewVerdict(level="degraded", sentence=problem)
    return OverviewVerdict(level="ok", sentence=ALL_OK_TEXT)


def attention_since(incident: Incident) -> datetime:
    return incident.escalated_at or incident.plan_at or incident.opened_at


def first_advice(advice: StoryAdvice) -> str:
    return advice.steps[0] if advice.steps else advice.text


def attention_item(incident: Incident, target_name: str, story: IncidentStory) -> AttentionItem:
    return AttentionItem(
        incident_id=incident.id,
        title=incident.title,
        target=target_name,
        severity=incident.severity,
        status=incident.status,
        status_label=story.status_label,
        since=attention_since(incident),
        summary=story.headline,
        advice=first_advice(story.what_you_should_do),
    )


async def needs_attention(session: AsyncSession) -> list[AttentionItem]:
    rows = await session.execute(
        select(Incident, Target.name)
        .join(Target, Target.id == Incident.target_id)
        .where(Incident.status.in_(NEEDS_YOU_STATUSES))
    )
    waiting = sorted(rows.all(), key=lambda row: attention_since(row[0]))
    items: list[AttentionItem] = []
    for incident, target_name in waiting:
        story = await get_incident_story(incident.id, session)
        items.append(attention_item(incident, target_name, story))
    return items


async def count_open_incidents(session: AsyncSession) -> int:
    open_statuses = [status.value for status in OPEN_STATUSES]
    count = await session.scalar(
        select(func.count()).select_from(Incident).where(Incident.status.in_(open_statuses))
    )
    return int(count or 0)


def event_sentence(event: IncidentEvent, title: str) -> str:
    if event.type == STATE_CHANGED:
        target_status = str(event.payload.get("to", ""))
        return f"{title}: {words.text_for(words.STATUS_LABELS, target_status)}"
    template = EVENT_SENTENCES.get(event.type)
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
        needs_you=len(attention),
        servers_up=sum(1 for server in servers if server.status == "up"),
        servers_total=len(servers),
        llm_keys_ok=working_keys,
        llm_keys_total=len(llm.keys),
    )
    llm_ok = llm.mode == REPLAY_MODE or working_keys > 0
    return Overview(
        verdict=overview_verdict(health, kpis.needs_you, servers, llm_ok),
        kpis=kpis,
        needs_attention=attention,
        activity=await recent_activity(session),
        servers=servers,
    )
