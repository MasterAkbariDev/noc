import time
import uuid
from collections.abc import AsyncIterator
from datetime import timedelta
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.prometheus import PrometheusReader
from noc.api.tickets import TicketStore
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import Peer
from noc.db.session import SessionFactory, transaction
from noc.peers.codes import parse_code
from noc.peers.signing import HEADER_PEER, HEADER_SIGNATURE, HEADER_TIMESTAMP, sign

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
PUBLIC = "https://owner.example"


@pytest.fixture
def settings(tmp_path: Path, database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
        secrets_dir=tmp_path / "secrets",
        node_name="owner-node",
        public_url=PUBLIC,
        _env_file=None,
    )


@pytest.fixture
async def client(sessions: SessionFactory, settings: Settings) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.tickets = TicketStore()
    app.state.prometheus = PrometheusReader(httpx.AsyncClient(timeout=2.0), "http://127.0.0.1:9")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        yield http


async def new_code(client: httpx.AsyncClient, name: str = "node-95") -> str:
    response = await client.post("/api/peers/join-codes", json={"name": name}, headers=AUTH)
    assert response.status_code == 200
    return response.json()["code"]


def signed_headers(
    method: str, path: str, peer_id: uuid.UUID, secret: str, body: bytes = b""
) -> dict[str, str]:
    timestamp = str(int(time.time()))
    return {
        HEADER_PEER: str(peer_id),
        HEADER_TIMESTAMP: timestamp,
        HEADER_SIGNATURE: sign(secret, method, path, timestamp, body),
    }


async def test_a_join_code_is_only_issued_to_an_admin(client: httpx.AsyncClient) -> None:
    anonymous = await client.post("/api/peers/join-codes", json={"name": "node-95"})
    assert anonymous.status_code == 401
    code = await new_code(client)
    assert parse_code(code).url == PUBLIC


async def test_the_other_node_pairs_with_the_code_and_then_reads_the_status(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    code = parse_code(await new_code(client))
    unpaired = await client.get(
        "/api/peer/status",
        headers=signed_headers("GET", "/api/peer/status", code.peer_id, code.secret),
    )
    assert unpaired.status_code == 403

    hello = await client.post(
        "/api/peer/hello",
        headers=signed_headers("POST", "/api/peer/hello", code.peer_id, code.secret),
    )
    assert hello.status_code == 200
    assert hello.json() == {"status": "paired"}

    status = await client.get(
        "/api/peer/status",
        headers=signed_headers("GET", "/api/peer/status", code.peer_id, code.secret),
    )
    assert status.status_code == 200
    body = status.json()
    assert body["node_name"] == "owner-node"
    assert body["servers"] == []
    assert body["incidents"] == []

    listed = (await client.get("/api/peers", headers=AUTH)).json()
    assert [row["status"] for row in listed] == ["paired"]
    assert "secret" not in str(listed)


async def test_a_wrong_key_or_a_tampered_request_is_refused(client: httpx.AsyncClient) -> None:
    code = parse_code(await new_code(client))
    wrong = await client.post(
        "/api/peer/hello",
        headers=signed_headers("POST", "/api/peer/hello", code.peer_id, "b" * 64),
    )
    assert wrong.status_code == 401
    unknown = await client.post(
        "/api/peer/hello",
        headers=signed_headers("POST", "/api/peer/hello", uuid.uuid4(), code.secret),
    )
    assert unknown.status_code == 401
    still_pending = await client.get(
        "/api/peer/status",
        headers=signed_headers("GET", "/api/peer/status", code.peer_id, code.secret),
    )
    assert still_pending.status_code == 403


async def test_an_expired_code_cannot_pair(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    code = parse_code(await new_code(client))
    async with transaction(sessions) as session:
        peer = await session.get(Peer, code.peer_id)
        assert peer is not None
        peer.expires_at = utc_now() - timedelta(seconds=1)
    hello = await client.post(
        "/api/peer/hello",
        headers=signed_headers("POST", "/api/peer/hello", code.peer_id, code.secret),
    )
    assert hello.status_code == 403
    assert "expired" in hello.text


async def test_removing_a_peer_cuts_off_its_access(client: httpx.AsyncClient) -> None:
    code = parse_code(await new_code(client))
    await client.post(
        "/api/peer/hello",
        headers=signed_headers("POST", "/api/peer/hello", code.peer_id, code.secret),
    )
    removed = await client.delete(f"/api/peers/{code.peer_id}", headers=AUTH)
    assert removed.status_code == 204
    after = await client.get(
        "/api/peer/status",
        headers=signed_headers("GET", "/api/peer/status", code.peer_id, code.secret),
    )
    assert after.status_code == 401


async def test_a_peer_row_is_stored_for_the_owner_without_its_secret(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    code = parse_code(await new_code(client, name="node-46"))
    async with sessions() as session:
        peer = await session.scalar(select(Peer).where(Peer.id == code.peer_id))
    assert peer is not None
    assert peer.direction == "serves"
    assert peer.name == "node-46"
    assert peer.url == ""
