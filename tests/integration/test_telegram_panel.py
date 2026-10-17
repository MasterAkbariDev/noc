import uuid
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.config import Settings
from noc.db.models import ActionRow, Approval, AuditEntry, Incident
from noc.db.session import SessionFactory, transaction
from noc.domain.incident_status import IncidentStatus
from noc.notify.telegram import TelegramUpdate
from noc.policy.models import Environment
from noc.secret_store import SecretStore
from noc.store.remediation import PENDING_APPROVAL
from noc.store.targets import add_target
from tests.integration.test_telegram_notifications import FakeBot, configure, say, text_update
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
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


def press(update_id: int, user_id: int, data: str) -> TelegramUpdate:
    return TelegramUpdate.model_validate(
        {
            "update_id": update_id,
            "callback_query": {
                "id": f"cb-{update_id}",
                "from": {"id": user_id, "first_name": "x"},
                "data": data,
                "message": {
                    "message_id": 9,
                    "chat": {"id": user_id, "type": "private"},
                    "from": {"id": user_id, "first_name": "x"},
                    "text": "menu",
                },
            },
        }
    )


async def make_incident(
    sessions: SessionFactory, status: IncidentStatus, environment: Environment = Environment.LAB
) -> tuple[uuid.UUID, uuid.UUID]:
    async with transaction(sessions) as session:
        target = await add_target(
            session,
            f"{environment.value}-1",
            "10.0.0.2",
            "https://host:9443",
            environment,
            KEY_ID,
        )
        incident = Incident(
            target_id=target.id,
            status=status.value,
            severity="critical",
            title="ServiceDown on host/svc:demo-shop",
            trace_id="t" * 32,
        )
        session.add(incident)
        await session.flush()
        return incident.id, target.id


async def make_pending_fix(
    sessions: SessionFactory, environment: Environment
) -> tuple[uuid.UUID, uuid.UUID]:
    incident_id, target_id = await make_incident(
        sessions, IncidentStatus.AWAITING_APPROVAL, environment
    )
    async with transaction(sessions) as session:
        action = ActionRow(
            incident_id=incident_id,
            target_id=target_id,
            action_type="restart_service",
            resource_id="svc:demo-shop",
            params={},
            status=PENDING_APPROVAL,
            permission_class="REQUIRES_APPROVAL",
            eligible=True,
            auto_executable=False,
            impact_score=10,
            policy_version="test",
            action_hash="a" * 64,
        )
        session.add(action)
        await session.flush()
        return incident_id, action.id


async def admin_ready(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> SecretStore:
    await configure(client, admins=[str(ADMIN)])
    store = SecretStore(settings.secrets_dir)
    await say(sessions, store, FakeBot(), text_update(1, ADMIN, "/start"))
    return store


async def test_menu_opens_from_a_command_and_its_buttons_show_sections(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    store = await admin_ready(client, sessions, settings)
    bot = FakeBot()
    await say(sessions, store, bot, text_update(2, ADMIN, "/menu"))
    await say(sessions, store, bot, press(3, ADMIN, "m:overview"))
    assert any("Overview" in text for _, text in bot.sent)


async def test_approving_a_fix_from_telegram_records_the_decision(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    store = await admin_ready(client, sessions, settings)
    _, action_id = await make_pending_fix(sessions, Environment.LAB)
    bot = FakeBot()
    await say(sessions, store, bot, press(4, ADMIN, f"a:{action_id}"))
    await say(sessions, store, bot, press(5, ADMIN, f"y:{action_id}"))
    await say(sessions, store, bot, press(6, ADMIN, f"do:ok:{action_id}"))
    async with sessions() as session:
        approval = await session.scalar(select(Approval).where(Approval.action_id == action_id))
    assert approval is not None
    assert approval.decision == "approved"
    assert approval.decided_by == f"telegram:{ADMIN}"


async def test_rejecting_a_fix_from_telegram_records_the_decision(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    store = await admin_ready(client, sessions, settings)
    _, action_id = await make_pending_fix(sessions, Environment.LAB)
    await say(sessions, store, FakeBot(), press(7, ADMIN, f"do:no:{action_id}"))
    async with sessions() as session:
        approval = await session.scalar(select(Approval).where(Approval.action_id == action_id))
    assert approval is not None
    assert approval.decision == "rejected"


async def test_production_fixes_are_refused_in_telegram(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    store = await admin_ready(client, sessions, settings)
    _, action_id = await make_pending_fix(sessions, Environment.PROD)
    bot = FakeBot()
    await say(sessions, store, bot, press(8, ADMIN, f"do:ok:{action_id}"))
    async with sessions() as session:
        approval = await session.scalar(select(Approval).where(Approval.action_id == action_id))
    assert approval is None


async def test_an_escalated_incident_can_be_closed_from_telegram(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    store = await admin_ready(client, sessions, settings)
    incident_id, _ = await make_incident(sessions, IncidentStatus.ESCALATED)
    await say(sessions, store, FakeBot(), press(9, ADMIN, f"cl:{incident_id}"))
    await say(sessions, store, FakeBot(), press(10, ADMIN, f"do:cl:{incident_id}"))
    async with sessions() as session:
        incident = await session.get(Incident, incident_id)
        audit = await session.scalar(
            select(AuditEntry).where(AuditEntry.action == "incident_closed")
        )
    assert incident is not None
    assert incident.status == IncidentStatus.CLOSED.value
    assert audit is not None
    assert audit.actor == f"telegram:{ADMIN}"


async def test_only_admins_can_press_the_fix_buttons(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    store = await admin_ready(client, sessions, settings)
    _, action_id = await make_pending_fix(sessions, Environment.LAB)
    await say(sessions, store, FakeBot(), press(11, OTHER, f"do:ok:{action_id}"))
    async with sessions() as session:
        approval = await session.scalar(select(Approval).where(Approval.action_id == action_id))
    assert approval is None


async def test_open_incidents_are_not_closable_from_telegram(
    client: httpx.AsyncClient, sessions: SessionFactory, settings: Settings
) -> None:
    store = await admin_ready(client, sessions, settings)
    incident_id, _ = await make_incident(sessions, IncidentStatus.INVESTIGATING)
    await say(sessions, store, FakeBot(), press(12, ADMIN, f"do:cl:{incident_id}"))
    async with sessions() as session:
        incident = await session.get(Incident, incident_id)
    assert incident is not None
    assert incident.status == IncidentStatus.INVESTIGATING.value
