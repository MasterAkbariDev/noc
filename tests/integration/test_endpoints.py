import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.config import Settings
from noc.db.session import SessionFactory

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


async def fake_ssh_server() -> tuple[asyncio.AbstractServer, int]:
    async def handle(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        writer.write(b"SSH-2.0-OpenSSH_9.6p1 Ubuntu\r\n")
        await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    return server, port


async def test_a_server_without_noc_is_checked_over_the_network(client: httpx.AsyncClient) -> None:
    server, port = await fake_ssh_server()
    try:
        added = await client.post(
            "/api/endpoints",
            json={"name": "box-test", "host": "127.0.0.1", "ssh_port": port},
            headers=AUTH,
        )
        assert added.status_code == 201
        endpoint_id = added.json()["id"]
        checked = await client.post(f"/api/endpoints/{endpoint_id}/check", headers=AUTH)
    finally:
        server.close()
        await server.wait_closed()
    assert checked.status_code == 200
    result = checked.json()["last_result"]
    assert result["ssh"]["open"] is True
    assert result["ssh"]["banner"] == "SSH-2.0-OpenSSH_9.6p1 Ubuntu"


async def test_a_closed_port_is_reported_as_down(client: httpx.AsyncClient) -> None:
    added = await client.post(
        "/api/endpoints",
        json={"name": "box-closed", "host": "127.0.0.1", "ssh_port": 1},
        headers=AUTH,
    )
    checked = await client.post(f"/api/endpoints/{added.json()['id']}/check", headers=AUTH)
    assert checked.json()["last_result"]["ssh"]["open"] is False


async def test_bad_addresses_and_duplicate_names_are_refused(client: httpx.AsyncClient) -> None:
    bad_host = await client.post(
        "/api/endpoints", json={"name": "x", "host": "rm -rf /", "ssh_port": 22}, headers=AUTH
    )
    bad_url = await client.post(
        "/api/endpoints",
        json={"name": "y", "host": "10.0.0.1", "ssh_port": 22, "url": "ftp://x"},
        headers=AUTH,
    )
    assert bad_host.status_code == 422
    assert bad_url.status_code == 422
    body = {"name": "dup", "host": "10.0.0.1", "ssh_port": 22}
    assert (await client.post("/api/endpoints", json=body, headers=AUTH)).status_code == 201
    assert (await client.post("/api/endpoints", json=body, headers=AUTH)).status_code == 409


async def test_anonymous_callers_cannot_add_endpoints(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/endpoints", json={"name": "z", "host": "10.0.0.1", "ssh_port": 22}
    )
    assert response.status_code == 401
