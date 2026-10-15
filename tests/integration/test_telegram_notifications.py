from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuditEntry, Incident, Notification
from noc.db.session import SessionFactory, transaction
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.notify.outbox import FAILED, MAX_ATTEMPTS, RETRY, SENT, deliver_once
from noc.notify.telegram import TelegramError
from noc.policy.models import Environment
from noc.secret_store import SecretStore
from noc.store.incidents import add_event, transition
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BOT = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
CHAT = "-1001234567890"


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        secrets_dir=tmp_path / "secrets",
        _env_file=None,
    )


@pytest.fixture
async def client(sessions: SessionFactory, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.tickets = TicketStore()
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


async def configure(client: httpx.AsyncClient, **events: bool) -> httpx.Response:
    await client.put("/api/notifications/telegram/token", json={"token": BOT}, headers=AUTH)
    return await client.put(
        "/api/notifications/telegram",
        json={
            "enabled": True,
            "chat_id": CHAT,
            "panel_url": "https://noc.example/",
            "events": {
                "opened": False,
                "approval": True,
                "escalated": True,
                "resolved": True,
                **events,
            },
        },
        headers=AUTH,
    )


class FakeSender:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.sent: list[tuple[str, str]] = []
        self.tokens: list[str] = []

    def factory(self, token: str, proxy: str | None) -> "FakeSender":
        self.tokens.append(token)
        return self

    async def send(self, chat_id: str, text: str) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise TelegramError("HTTP 502: bad gateway")
        self.sent.append((chat_id, text))


async def open_and_escalate(sessions: SessionFactory) -> Incident:
    async with transaction(sessions) as session:
        target = await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
        incident = Incident(
            target_id=target.id,
            status=IncidentStatus.NEW.value,
            severity="critical",
            title="ServiceDown on demo-1/svc:demo-shop",
            trace_id="t" * 32,
        )
        session.add(incident)
        await session.flush()
        await add_event(session, incident.id, "incident_opened", "correlator", {})
        await transition(session, incident, IncidentStatus.INVESTIGATING, "supervisor")
        await transition(
            session,
            incident,
            IncidentStatus.ESCALATED,
            "supervisor",
            EscalationReason.INVESTIGATION_FAILED,
        )
        return incident


async def test_token_is_stored_as_a_secret_and_only_its_end_is_shown(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    response = await client.put(
        "/api/notifications/telegram/token", json={"token": BOT}, headers=AUTH
    )
    assert response.status_code == 200
    assert response.json()["token_last4"] == BOT[-4:]
    assert BOT not in response.text
    assert SecretStore(settings.secrets_dir).read("telegram-bot") == BOT
    async with sessions() as session:
        audit = list(await session.scalars(select(AuditEntry.payload)))
    assert all(BOT not in str(payload) for payload in audit)


async def test_bad_tokens_and_chat_ids_are_refused(client: httpx.AsyncClient) -> None:
    token = await client.put(
        "/api/notifications/telegram/token", json={"token": "nope"}, headers=AUTH
    )
    assert token.status_code == 422
    await client.put("/api/notifications/telegram/token", json={"token": BOT}, headers=AUTH)
    chat = await client.put(
        "/api/notifications/telegram", json={"enabled": True, "chat_id": "a b"}, headers=AUTH
    )
    assert chat.status_code == 422


async def test_notifications_cannot_be_turned_on_without_a_token(client: httpx.AsyncClient) -> None:
    response = await client.put(
        "/api/notifications/telegram", json={"enabled": True, "chat_id": CHAT}, headers=AUTH
    )
    assert response.status_code == 422
    assert "bot token" in response.json()["detail"]


async def test_removing_the_token_turns_notifications_off(client: httpx.AsyncClient) -> None:
    await configure(client)
    response = await client.delete("/api/notifications/telegram/token", headers=AUTH)
    assert response.json()["enabled"] is False
    assert response.json()["token_last4"] is None


async def test_escalation_is_sent_once_with_a_link_and_the_open_event_is_skipped(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    incident = await open_and_escalate(sessions)
    sender = FakeSender()
    store = SecretStore(settings.secrets_dir)
    assert await deliver_once(sessions, store, sender.factory) == 1
    assert await deliver_once(sessions, store, sender.factory) == 0
    assert len(sender.sent) == 1
    chat_id, text = sender.sent[0]
    assert chat_id == CHAT
    assert text.startswith("[NOC] Escalated to a person: ServiceDown on demo-1/svc:demo-shop")
    assert f"https://noc.example/incidents/{incident.id}" in text
    assert sender.tokens == [BOT]
    async with sessions() as session:
        statuses = list(await session.scalars(select(Notification.status)))
    assert sorted(statuses) == [SENT, SENT, SENT]


async def test_nothing_is_sent_while_notifications_are_off(
    sessions: SessionFactory, settings: Settings
) -> None:
    await open_and_escalate(sessions)
    sender = FakeSender()
    assert await deliver_once(sessions, SecretStore(settings.secrets_dir), sender.factory) == 0
    assert sender.sent == []


async def test_events_from_before_turning_on_are_not_replayed(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await open_and_escalate(sessions)
    await configure(client)
    sender = FakeSender()
    assert await deliver_once(sessions, SecretStore(settings.secrets_dir), sender.factory) == 0


async def test_failures_are_retried_with_backoff_then_given_up(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    await open_and_escalate(sessions)
    store = SecretStore(settings.secrets_dir)
    sender = FakeSender(failures=MAX_ATTEMPTS)
    now = utc_now()
    clock_value = [now]

    assert await deliver_once(sessions, store, sender.factory, lambda: clock_value[0]) == 0
    async with sessions() as session:
        row = await session.scalar(select(Notification).where(Notification.status != SENT))
    assert row is not None
    assert row.status == RETRY
    assert row.attempts == 1
    assert row.last_error == "HTTP 502: bad gateway"
    assert await deliver_once(sessions, store, sender.factory, lambda: clock_value[0]) == 0
    for _ in range(MAX_ATTEMPTS):
        clock_value[0] = clock_value[0] + timedelta(hours=2)
        await deliver_once(sessions, store, sender.factory, lambda: clock_value[0])
    async with sessions() as session:
        row = await session.scalar(select(Notification).where(Notification.status != SENT))
    assert row is not None
    assert row.status == FAILED
    assert row.attempts == MAX_ATTEMPTS
    assert sender.sent == []


async def test_the_test_endpoint_sends_through_the_sender(
    client: httpx.AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    await configure(client)
    sent: list[tuple[str, str]] = []

    class Recorder:
        def __init__(self, token: str, proxy: str | None = None) -> None:
            assert token == BOT

        async def send(self, chat_id: str, text: str) -> None:
            sent.append((chat_id, text))

    monkeypatch.setattr("noc.api.notifications.TelegramSender", Recorder)
    response = await client.post("/api/notifications/telegram/test", headers=AUTH)
    assert response.json() == {"ok": True, "detail": "sent; check the chat"}
    assert sent
    assert sent[0][0] == CHAT


async def test_the_test_endpoint_needs_a_token_and_chat(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/notifications/telegram/test", headers=AUTH)
    assert response.status_code == 409
