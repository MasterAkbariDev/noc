import time
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.config import Settings
from noc.db.models import AuditEntry, Target
from noc.db.session import SessionFactory, transaction
from noc.peers.codes import parse_code
from noc.peers.signing import HEADER_PEER, HEADER_SIGNATURE, HEADER_TIMESTAMP, sign
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
        secrets_dir=tmp_path / "secrets",
        node_name="owner-node",
        public_url="https://owner.example",
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


async def add_demo(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "127.0.0.1", "https://127.0.0.1:9443", Environment.LAB, KEY_ID
        )


async def test_an_admin_sets_the_mode_and_it_is_audited(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await add_demo(sessions)
    changed = await client.put(
        "/api/servers/demo-1/automation", json={"level": "approval_required"}, headers=AUTH
    )
    assert changed.status_code == 200
    assert changed.json() == {"name": "demo-1", "automation_level": "approval_required"}
    async with sessions() as session:
        target = await session.scalar(select(Target).where(Target.name == "demo-1"))
        audit = await session.scalar(
            select(AuditEntry).where(AuditEntry.action == "server_automation_set")
        )
    assert target is not None
    assert target.automation_level == "approval_required"
    assert audit is not None
    assert audit.payload["from"] == "auto_safe"
    assert audit.payload["to"] == "approval_required"


async def test_an_unknown_mode_is_refused(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await add_demo(sessions)
    response = await client.put(
        "/api/servers/demo-1/automation", json={"level": "rm -rf"}, headers=AUTH
    )
    assert response.status_code == 422


async def test_anonymous_callers_cannot_change_the_mode(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await add_demo(sessions)
    response = await client.put("/api/servers/demo-1/automation", json={"level": "observe_only"})
    assert response.status_code == 401


async def test_the_shared_status_carries_the_server_label(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await add_demo(sessions)
    await client.put("/api/servers/demo-1/label", json={"label": "Stage 104"}, headers=AUTH)
    code = parse_code(
        (
            await client.post("/api/peers/join-codes", json={"name": "node-follower"}, headers=AUTH)
        ).json()["code"]
    )
    timestamp = str(int(time.time()))
    hello_headers = {
        HEADER_PEER: str(code.peer_id),
        HEADER_TIMESTAMP: timestamp,
        HEADER_SIGNATURE: sign(code.secret, "POST", "/api/peer/hello", timestamp, b""),
    }
    assert (await client.post("/api/peer/hello", headers=hello_headers)).status_code == 200
    timestamp = str(int(time.time()))
    status_headers = {
        HEADER_PEER: str(code.peer_id),
        HEADER_TIMESTAMP: timestamp,
        HEADER_SIGNATURE: sign(code.secret, "GET", "/api/peer/status", timestamp, b""),
    }
    body = (await client.get("/api/peer/status", headers=status_headers)).json()
    assert body["targets"][0]["label"] == "Stage 104"
    assert body["targets"][0]["name"] == "demo-1"
