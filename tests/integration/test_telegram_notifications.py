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
from noc.notify.bot import poll_once
from noc.notify.outbox import FAILED, MAX_ATTEMPTS, RETRY, SENT, deliver_once
from noc.notify.telegram import Keyboard, TelegramError, TelegramUpdate
from noc.policy.models import Environment
from noc.secret_store import SecretStore
from noc.store.incidents import add_event, transition
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
BOT = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"
ADMIN = 111111
OTHER = 222222


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


async def configure(client: httpx.AsyncClient, admins: list[str] | None = None) -> httpx.Response:
    await client.put("/api/notifications/telegram/token", json={"token": BOT}, headers=AUTH)
    return await client.put(
        "/api/notifications/telegram",
        json={"panel_url": "https://noc.example/", "admins": admins or [str(ADMIN), "@sara_ops"]},
        headers=AUTH,
    )


def text_update(
    update_id: int, user_id: int, text: str, username: str | None = None
) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": update_id,
            "message": {
                "message_id": update_id,
                "chat": {"id": user_id, "type": "private"},
                "from": {"id": user_id, "username": username, "first_name": "x"},
                "text": text,
            },
        }
    )


class FakeBot:
    def __init__(self, failures: int = 0) -> None:
        self.failures = failures
        self.pending: list[TelegramUpdate] = []
        self.offsets: list[int | None] = []
        self.sent: list[tuple[str, str]] = []
        self.keyboards: list[Keyboard | None] = []
        self.tokens: list[str] = []

    def factory(self, token: str, proxy: str | None) -> "FakeBot":
        self.tokens.append(token)
        return self

    async def send(
        self, chat_id: str, text: str, keyboard: Keyboard | None = None, html: bool = False
    ) -> None:
        if self.failures > 0:
            self.failures -= 1
            raise TelegramError("HTTP 502: bad gateway")
        self.sent.append((chat_id, text))
        self.keyboards.append(keyboard)

    async def edit(
        self,
        chat_id: str,
        message_id: int,
        text: str,
        keyboard: Keyboard | None = None,
        html: bool = False,
    ) -> None:
        self.sent.append((chat_id, text))

    async def answer(self, callback_id: str, text: str) -> None:
        return None

    async def updates(self, offset: int | None) -> list[TelegramUpdate]:
        self.offsets.append(offset)
        batch, self.pending = self.pending, []
        return batch


async def say(
    sessions: SessionFactory, store: SecretStore, bot: FakeBot, *updates: TelegramUpdate
) -> None:
    bot.pending.extend(updates)
    assert await poll_once(sessions, store, bot.factory) is True


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


async def test_bad_tokens_and_admin_handles_are_refused(client: httpx.AsyncClient) -> None:
    token = await client.put(
        "/api/notifications/telegram/token", json={"token": "nope"}, headers=AUTH
    )
    assert token.status_code == 422
    admins = await client.put(
        "/api/notifications/telegram", json={"admins": ["-100123", "a b"]}, headers=AUTH
    )
    assert admins.status_code == 422
    url = await client.put(
        "/api/notifications/telegram", json={"panel_url": "ftp://x"}, headers=AUTH
    )
    assert url.status_code == 422


async def test_admins_are_listed_as_waiting_until_they_write_to_the_bot(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    response = await configure(client)
    assert [(item["handle"], item["linked"]) for item in response.json()["admins"]] == [
        (str(ADMIN), False),
        ("@sara_ops", False),
    ]
    store = SecretStore(settings.secrets_dir)
    await say(sessions, store, FakeBot(), text_update(1, OTHER, "/start", "Sara_Ops"))
    listed = await client.get("/api/notifications/telegram", headers=AUTH)
    assert [item["linked"] for item in listed.json()["admins"]] == [False, True]


async def test_the_bot_remembers_its_offset_and_answers_strangers(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    store = SecretStore(settings.secrets_dir)
    bot = FakeBot()
    await say(sessions, store, bot, text_update(41, 555555, "/pause"))
    await say(sessions, store, bot)
    assert bot.offsets == [None, 42]
    assert "555555" in bot.sent[0][1]
    listed = await client.get("/api/notifications/telegram", headers=AUTH)
    assert listed.json()["paused"] is False


async def test_admins_manage_the_bot_from_telegram_and_it_is_audited(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    store = SecretStore(settings.secrets_dir)
    await say(
        sessions,
        store,
        FakeBot(),
        text_update(1, ADMIN, "/start"),
        text_update(2, ADMIN, "/add 333333"),
        text_update(3, ADMIN, "/pause"),
    )
    listed = (await client.get("/api/notifications/telegram", headers=AUTH)).json()
    assert [item["handle"] for item in listed["admins"]] == [str(ADMIN), "@sara_ops", "333333"]
    assert listed["paused"] is True
    async with sessions() as session:
        actions = list(
            await session.scalars(
                select(AuditEntry.action).where(AuditEntry.actor == f"telegram:{ADMIN}")
            )
        )
    assert actions == ["telegram_admin_linked", "telegram_admin_added", "telegram_paused"]


async def test_escalation_reaches_each_linked_admin_once_with_a_panel_button(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    store = SecretStore(settings.secrets_dir)
    bot = FakeBot()
    await say(sessions, store, bot, text_update(1, ADMIN, "/start"))
    bot.sent.clear()
    incident = await open_and_escalate(sessions)
    assert await deliver_once(sessions, store, bot.factory) == 1
    assert await deliver_once(sessions, store, bot.factory) == 0
    [(chat_id, text)] = bot.sent
    assert chat_id == str(ADMIN)
    assert text.startswith(
        "🚨 <b>Escalated to a person</b>\n<b>ServiceDown on demo-1/svc:demo-shop</b>"
    )
    assert "<b>What you should do</b>" in text
    assert "https://" not in text
    keyboard = bot.keyboards[-1]
    assert keyboard is not None
    assert keyboard[-1][0].url == f"https://noc.example/incidents/{incident.id}"
    async with sessions() as session:
        statuses = list(await session.scalars(select(Notification.status)))
    assert sorted(statuses) == [SENT, SENT, SENT]


async def test_muted_and_paused_admins_get_nothing(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    store = SecretStore(settings.secrets_dir)
    bot = FakeBot()
    await say(
        sessions,
        store,
        bot,
        text_update(1, ADMIN, "/start"),
        text_update(2, ADMIN, "/mute"),
        text_update(3, OTHER, "/start", "sara_ops"),
        text_update(4, OTHER, "/pause"),
    )
    bot.sent.clear()
    await open_and_escalate(sessions)
    assert await deliver_once(sessions, store, bot.factory) == 0
    await say(sessions, store, bot, text_update(5, OTHER, "/resume"))
    bot.sent.clear()
    assert await deliver_once(sessions, store, bot.factory) == 0


async def test_nothing_is_sent_without_a_token(
    sessions: SessionFactory, settings: Settings
) -> None:
    await open_and_escalate(sessions)
    bot = FakeBot()
    store = SecretStore(settings.secrets_dir)
    assert await deliver_once(sessions, store, bot.factory) == 0
    assert await poll_once(sessions, store, bot.factory) is False
    assert bot.sent == []


async def test_events_from_before_an_admin_wrote_to_the_bot_are_not_replayed(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    await open_and_escalate(sessions)
    store = SecretStore(settings.secrets_dir)
    bot = FakeBot()
    await say(sessions, store, bot, text_update(1, ADMIN, "/start"))
    bot.sent.clear()
    assert await deliver_once(sessions, store, bot.factory) == 0


async def test_failures_are_retried_with_backoff_then_given_up(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    await configure(client)
    store = SecretStore(settings.secrets_dir)
    await say(sessions, store, FakeBot(), text_update(1, ADMIN, "/start"))
    await open_and_escalate(sessions)
    bot = FakeBot(failures=MAX_ATTEMPTS)
    now = utc_now()
    clock_value = [now]

    assert await deliver_once(sessions, store, bot.factory, lambda: clock_value[0]) == 0
    async with sessions() as session:
        row = await session.scalar(select(Notification).where(Notification.status != SENT))
    assert row is not None
    assert row.status == RETRY
    assert row.attempts == 1
    assert row.last_error == "HTTP 502: bad gateway"
    assert await deliver_once(sessions, store, bot.factory, lambda: clock_value[0]) == 0
    for _ in range(MAX_ATTEMPTS):
        clock_value[0] = clock_value[0] + timedelta(hours=2)
        await deliver_once(sessions, store, bot.factory, lambda: clock_value[0])
    async with sessions() as session:
        row = await session.scalar(select(Notification).where(Notification.status != SENT))
    assert row is not None
    assert row.status == FAILED
    assert row.attempts == MAX_ATTEMPTS
    assert bot.sent == []


async def test_removing_the_token_is_shown(client: httpx.AsyncClient) -> None:
    await configure(client)
    response = await client.delete("/api/notifications/telegram/token", headers=AUTH)
    assert response.json()["token_last4"] is None


async def test_the_test_endpoint_messages_every_linked_admin(
    client: httpx.AsyncClient,
    sessions: SessionFactory,
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await configure(client)
    await say(
        sessions, SecretStore(settings.secrets_dir), FakeBot(), text_update(1, ADMIN, "/start")
    )
    sent: list[tuple[str, str]] = []

    class Recorder:
        def __init__(self, token: str, proxy: str | None = None) -> None:
            assert token == BOT

        async def send(self, chat_id: str, text: str) -> None:
            sent.append((chat_id, text))

    monkeypatch.setattr("noc.api.notifications.TelegramSender", Recorder)
    response = await client.post("/api/notifications/telegram/test", headers=AUTH)
    assert response.json() == {"ok": True, "detail": "sent to 1 admin(s)"}
    assert [chat for chat, _ in sent] == [str(ADMIN)]


async def test_the_test_endpoint_needs_a_linked_admin(client: httpx.AsyncClient) -> None:
    await configure(client)
    response = await client.post("/api/notifications/telegram/test", headers=AUTH)
    assert response.status_code == 409
