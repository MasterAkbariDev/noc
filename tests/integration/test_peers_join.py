from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import text

from noc.api.app import create_app
from noc.api.prometheus import PrometheusReader
from noc.api.tickets import TicketStore
from noc.config import Settings
from noc.db.base import Base
from noc.db.session import SessionFactory, create_engine, create_session_factory

pytestmark = pytest.mark.integration

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
OWNER_PUBLIC = "https://owner.example"
FOLLOWER_DB = "noc_test_peers_follower"


def other_database(url: str, name: str) -> str:
    base, _, _ = url.rpartition("/")
    return f"{base}/{name}"


@pytest.fixture
async def follower_sessions(database_url: str) -> AsyncIterator[SessionFactory]:
    admin = create_engine(other_database(database_url, "postgres"))
    async with admin.connect() as connection:
        connection = await connection.execution_options(isolation_level="AUTOCOMMIT")
        await connection.execute(text(f"DROP DATABASE IF EXISTS {FOLLOWER_DB}"))
        await connection.execute(text(f"CREATE DATABASE {FOLLOWER_DB}"))
    await admin.dispose()
    engine = create_engine(other_database(database_url, FOLLOWER_DB))
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    yield create_session_factory(engine)
    await engine.dispose()


def settings_for(tmp_path: Path, database_url: str, name: str, public: str = "") -> Settings:
    return Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
        secrets_dir=tmp_path / name / "secrets",
        node_name=name,
        public_url=public,
        _env_file=None,
    )


async def client_for(app: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://noc")  # type: ignore[arg-type]


@pytest.fixture
async def owner(
    tmp_path: Path, sessions: SessionFactory, database_url: str
) -> AsyncIterator[tuple[object, httpx.AsyncClient]]:
    settings = settings_for(tmp_path, database_url, "owner-node", OWNER_PUBLIC)
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    app.state.tickets = TicketStore()
    app.state.prometheus = PrometheusReader(httpx.AsyncClient(timeout=2.0), "http://127.0.0.1:9")
    http = await client_for(app)
    yield app, http
    await http.aclose()


@pytest.fixture
async def follower(
    tmp_path: Path,
    follower_sessions: SessionFactory,
    database_url: str,
    owner: tuple[object, httpx.AsyncClient],
) -> AsyncIterator[httpx.AsyncClient]:
    owner_app, _ = owner
    settings = settings_for(tmp_path, other_database(database_url, FOLLOWER_DB), "follower-node")
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = follower_sessions
    app.state.tickets = TicketStore()
    app.state.prometheus = PrometheusReader(httpx.AsyncClient(timeout=2.0), "http://127.0.0.1:9")
    app.state.peer_transport = httpx.ASGITransport(app=owner_app)  # type: ignore[arg-type]
    http = await client_for(app)
    yield http
    await http.aclose()


async def test_the_follower_joins_with_a_code_and_reads_the_owner_status(
    owner: tuple[object, httpx.AsyncClient], follower: httpx.AsyncClient
) -> None:
    _, owner_http = owner
    created = await owner_http.post(
        "/api/peers/join-codes", json={"name": "node-follower"}, headers=AUTH
    )
    assert created.status_code == 200
    code = created.json()["code"]

    joined = await follower.post("/api/peers/join", json={"code": code}, headers=AUTH)
    assert joined.status_code == 200, joined.text
    peer = joined.json()
    assert peer["direction"] == "follows"
    assert peer["status"] == "paired"

    refreshed = await follower.post(f"/api/peers/{peer['id']}/refresh", headers=AUTH)
    assert refreshed.status_code == 200, refreshed.text
    view = refreshed.json()
    assert view["name"] == "owner-node"
    assert view["last_error"] is None
    assert view["last_status"]["node_name"] == "owner-node"
    assert view["last_status"]["servers"] == []


async def test_a_code_works_once(
    owner: tuple[object, httpx.AsyncClient], follower: httpx.AsyncClient
) -> None:
    _, owner_http = owner
    code = (
        await owner_http.post("/api/peers/join-codes", json={"name": "node-follower"}, headers=AUTH)
    ).json()["code"]
    assert (
        await follower.post("/api/peers/join", json={"code": code}, headers=AUTH)
    ).status_code == 200
    again = await follower.post("/api/peers/join", json={"code": code}, headers=AUTH)
    assert again.status_code == 422
    assert "already" in again.text


async def test_a_follower_without_a_pairing_cannot_refresh(
    owner: tuple[object, httpx.AsyncClient], follower: httpx.AsyncClient
) -> None:
    _, owner_http = owner
    code = (
        await owner_http.post("/api/peers/join-codes", json={"name": "node-follower"}, headers=AUTH)
    ).json()["code"]
    peer_id = (await follower.post("/api/peers/join", json={"code": code}, headers=AUTH)).json()[
        "id"
    ]
    await owner_http.delete(f"/api/peers/{peer_id}", headers=AUTH)
    refreshed = await follower.post(f"/api/peers/{peer_id}/refresh", headers=AUTH)
    assert refreshed.status_code == 200
    assert refreshed.json()["last_error"] is not None
