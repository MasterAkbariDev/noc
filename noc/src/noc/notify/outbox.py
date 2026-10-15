from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final, Protocol

import structlog
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.base import utc_now
from noc.db.models import Incident, IncidentEvent, Notification, Target
from noc.db.session import SessionFactory, transaction
from noc.notify.settings import (
    NotifyEvents,
    TelegramSettings,
    load_settings,
    read_proxy,
    read_token,
)
from noc.notify.telegram import TelegramError, TelegramSender
from noc.secret_store import SecretStore

logger = structlog.get_logger(__name__)

CHANNEL: Final = "telegram"
SENT: Final = "sent"
RETRY: Final = "retry"
FAILED: Final = "failed"
MAX_ATTEMPTS: Final = 5
RETRY_BASE_SECONDS: Final = 30
LOOKBACK: Final = timedelta(hours=1)
BATCH: Final = 20
SUMMARY_MAX_LENGTH: Final = 400
WATCHED_TYPES: Final = (
    "incident_opened",
    "approval_requested",
    "approval_expired",
    "state_changed",
)
RESOLVED_STATES: Final = frozenset({"RESOLVED", "SELF_RESOLVED"})


class Sender(Protocol):
    async def send(self, chat_id: str, text: str) -> None: ...


SenderFactory = Callable[[str, str | None], Sender]


@dataclass(frozen=True)
class Outgoing:
    event_id: int
    attempts: int
    text: str


def event_kind(event: IncidentEvent) -> str | None:
    if event.type == "incident_opened":
        return "opened"
    if event.type in ("approval_requested", "approval_expired"):
        return "approval"
    if event.type == "state_changed":
        target = str(event.payload.get("to", ""))
        if target == "ESCALATED":
            return "escalated"
        if target in RESOLVED_STATES:
            return "resolved"
    return None


def wanted(event: IncidentEvent, events: NotifyEvents) -> bool:
    kind = event_kind(event)
    return kind is not None and bool(getattr(events, kind))


def headline(event: IncidentEvent) -> str:
    if event.type == "incident_opened":
        return "New incident"
    if event.type == "approval_requested":
        return "Approval needed"
    if event.type == "approval_expired":
        return "Approval request expired"
    target = str(event.payload.get("to", ""))
    if target == "ESCALATED":
        return "Escalated to a person"
    return "Resolved" if target == "RESOLVED" else "Resolved on its own"


def message_for(event: IncidentEvent, incident: Incident, target: Target, panel_url: str) -> str:
    lines = [
        f"[NOC] {headline(event)}: {incident.title}",
        f"Server: {target.name} ({target.environment})",
    ]
    reason = event.payload.get("reason") or incident.escalation_reason
    if event.type == "state_changed" and reason:
        lines.append(f"Reason: {str(reason).replace('_', ' ')}")
    if incident.root_cause_code:
        confidence = f" ({incident.confidence:.0%})" if incident.confidence is not None else ""
        lines.append(f"Root cause: {incident.root_cause_code.replace('_', ' ')}{confidence}")
    if panel_url:
        lines.append(f"{panel_url}/incidents/{incident.id}")
    return "\n".join(lines)


async def pending(
    session: AsyncSession, since: datetime, now: datetime
) -> list[tuple[IncidentEvent, int]]:
    rows = await session.execute(
        select(IncidentEvent, Notification.attempts)
        .outerjoin(
            Notification,
            and_(Notification.event_id == IncidentEvent.id, Notification.channel == CHANNEL),
        )
        .where(
            IncidentEvent.type.in_(WATCHED_TYPES),
            or_(
                and_(Notification.event_id.is_(None), IncidentEvent.ts >= since),
                and_(Notification.status == RETRY, Notification.next_attempt_at <= now),
            ),
        )
        .order_by(IncidentEvent.id)
        .limit(BATCH)
    )
    return [(event, attempts or 0) for event, attempts in rows.all()]


async def collect(
    session: AsyncSession, settings: TelegramSettings, now: datetime
) -> list[Outgoing]:
    since = max(now - LOOKBACK, settings.enabled_at or now)
    outgoing: list[Outgoing] = []
    for event, attempts in await pending(session, since, now):
        if not wanted(event, settings.events):
            await record(session, event.id, SENT, attempts, None, now)
            continue
        incident = await session.get_one(Incident, event.incident_id)
        target = await session.get_one(Target, incident.target_id)
        outgoing.append(
            Outgoing(event.id, attempts, message_for(event, incident, target, settings.panel_url))
        )
    return outgoing


async def record(
    session: AsyncSession,
    event_id: int,
    status: str,
    attempts: int,
    error: str | None,
    now: datetime,
) -> None:
    row = await session.get(Notification, (event_id, CHANNEL))
    if row is None:
        row = Notification(event_id=event_id, channel=CHANNEL, status=status, attempts=attempts)
        session.add(row)
    row.status = status
    row.attempts = attempts
    row.last_error = error
    row.sent_at = now if status == SENT else None
    row.next_attempt_at = (
        now + timedelta(seconds=RETRY_BASE_SECONDS * 2**attempts) if status == RETRY else None
    )
    await session.flush()


def default_sender(token: str, proxy: str | None) -> Sender:
    return TelegramSender(token, proxy)


async def deliver_once(
    sessions: SessionFactory,
    store: SecretStore,
    make_sender: SenderFactory = default_sender,
    clock: Callable[[], datetime] = utc_now,
) -> int:
    now = clock()
    async with transaction(sessions) as session:
        settings = await load_settings(session)
        if not settings.enabled or not settings.chat_id:
            return 0
        outgoing = await collect(session, settings, now)
    if not outgoing:
        return 0
    token = await read_token(store)
    if not token:
        return 0
    sender = make_sender(token, await read_proxy(store))
    results: list[tuple[Outgoing, str | None]] = []
    for item in outgoing:
        try:
            await sender.send(settings.chat_id, item.text)
        except TelegramError as failure:
            logger.warning("telegram_send_failed", event_id=item.event_id, error=str(failure))
            results.append((item, str(failure)))
            continue
        results.append((item, None))
    async with transaction(sessions) as session:
        for item, problem in results:
            attempts = item.attempts + 1
            status = SENT if problem is None else (FAILED if attempts >= MAX_ATTEMPTS else RETRY)
            await record(session, item.event_id, status, attempts, problem, clock())
    return sum(1 for _, problem in results if problem is None)
