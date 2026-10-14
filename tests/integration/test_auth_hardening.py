import asyncio
import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import func, select
from typer.testing import CliRunner

from noc.api import events
from noc.api.app import create_app
from noc.api.events import CONNECTED_FRAME, event_frames, session_check
from noc.api.tickets import TicketGrant, TicketStore
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, sha256_hex
from noc.auth.users import create_user
from noc.cli.main import app as cli_app
from noc.config import Settings
from noc.db.models import LoginFailure, User
from noc.db.session import SessionFactory, transaction

pytestmark = pytest.mark.integration

TOKEN = "test-token"
BASE_URL = "http://localhost"
PASSWORD = "correct horse battery"
WRONG = "wrong horse battery"
LOGIN_PATH = "/api/auth/login"
LOGOUT_PATH = "/api/auth/logout"
ME_PATH = "/api/auth/me"


def settings_for(database_url: str) -> Settings:
    return Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
        _env_file=None,
    )


@pytest.fixture
async def app(sessions: SessionFactory, database_url: str) -> FastAPI:
    settings = settings_for(database_url)
    application = create_app(settings)
    application.state.settings = settings
    application.state.sessions = sessions
    application.state.tickets = TicketStore()
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with new_client(app) as http:
        yield http


def new_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)


async def add_user(sessions: SessionFactory, username: str, role: Role) -> uuid.UUID:
    async with transaction(sessions) as session:
        user = await create_user(session, username, PASSWORD, role, "cli")
        return user.id


async def login(http: httpx.AsyncClient, username: str, password: str = PASSWORD) -> int:
    response = await http.post(LOGIN_PATH, json={"username": username, "password": password})
    return response.status_code


def csrf_headers(http: httpx.AsyncClient) -> dict[str, str]:
    return {CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""}


async def failure_rows(sessions: SessionFactory) -> int:
    async with sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(LoginFailure)) or 0)


async def test_parallel_wrong_logins_cannot_exceed_the_username_limit(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await add_user(sessions, "alice", Role.ADMIN)
    statuses = await asyncio.gather(*(login(client, "alice", WRONG) for _ in range(12)))
    assert statuses.count(401) <= 5
    assert statuses.count(401) + statuses.count(429) == 12
    assert await failure_rows(sessions) == statuses.count(401)


async def test_a_right_password_leaves_no_failure_behind(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await add_user(sessions, "alice", Role.ADMIN)
    assert await login(client, "alice") == 200
    assert await failure_rows(sessions) == 0


async def test_logout_without_the_csrf_header_keeps_the_session(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await add_user(sessions, "alice", Role.ADMIN)
    assert await login(client, "alice") == 200
    refused = await client.post(LOGOUT_PATH)
    assert refused.status_code == 403
    assert (await client.get(ME_PATH)).status_code == 200
    accepted = await client.post(LOGOUT_PATH, headers=csrf_headers(client))
    assert accepted.status_code == 204
    assert (await client.get(ME_PATH)).status_code == 401


async def test_a_non_ascii_bearer_header_is_refused_not_crashed(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/incidents", headers={"Authorization": b"Bearer \xe9t\xe9"})
    assert response.status_code == 401


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
async def test_the_api_description_is_not_served(client: httpx.AsyncClient, path: str) -> None:
    assert (await client.get(path)).status_code == 404


async def test_the_token_cannot_disable_the_last_admin(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    admin_id = await add_user(sessions, "alice", Role.ADMIN)
    response = await client.post(
        f"/api/users/{admin_id}/disable", headers={"Authorization": f"Bearer {TOKEN}"}
    )
    assert response.status_code == 409
    demote = await client.post(
        f"/api/users/{admin_id}/role",
        json={"role": "operator"},
        headers={"Authorization": f"Bearer {TOKEN}"},
    )
    assert demote.status_code == 409


async def test_two_admins_disabling_each_other_leave_one_admin(
    app: FastAPI, sessions: SessionFactory
) -> None:
    alice_id = await add_user(sessions, "alice", Role.ADMIN)
    bob_id = await add_user(sessions, "bob", Role.ADMIN)
    async with new_client(app) as alice, new_client(app) as bob:
        assert await login(alice, "alice") == 200
        assert await login(bob, "bob") == 200
        results = await asyncio.gather(
            alice.post(f"/api/users/{bob_id}/disable", headers=csrf_headers(alice)),
            bob.post(f"/api/users/{alice_id}/disable", headers=csrf_headers(bob)),
        )
    assert sorted(response.status_code for response in results) == [200, 409]
    async with sessions() as session:
        active = await session.scalar(
            select(func.count())
            .select_from(User)
            .where(User.role == Role.ADMIN.value, User.disabled.is_(False))
        )
    assert active == 1


async def test_an_admin_cannot_reset_their_own_password_through_the_users_api(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    alice_id = await add_user(sessions, "alice", Role.ADMIN)
    assert await login(client, "alice") == 200
    response = await client.post(
        f"/api/users/{alice_id}/password",
        json={"new_password": "another long password"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 409
    assert (await client.get(ME_PATH)).status_code == 200


async def test_creating_the_same_user_twice_at_once_is_a_conflict(
    client: httpx.AsyncClient,
) -> None:
    auth = {"Authorization": f"Bearer {TOKEN}"}
    body = {"username": "carol", "password": PASSWORD, "role": "viewer"}
    results = await asyncio.gather(
        client.post("/api/users", json=body, headers=auth),
        client.post("/api/users", json=body, headers=auth),
    )
    assert sorted(response.status_code for response in results) == [200, 409]


async def test_cli_unlock_clears_the_failures_of_a_locked_out_user(
    client: httpx.AsyncClient,
    sessions: SessionFactory,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await add_user(sessions, "alice", Role.ADMIN)
    for _ in range(5):
        assert await login(client, "alice", WRONG) == 401
    assert await login(client, "alice") == 429
    monkeypatch.setattr("noc.cli.main.get_settings", lambda: settings_for(database_url))
    result = await asyncio.to_thread(CliRunner().invoke, cli_app, ["users", "unlock", "alice"])
    assert result.exit_code == 0, result.output
    assert "cleared 5" in result.output
    assert await login(client, "alice") == 200


async def test_a_stream_ends_once_its_session_is_gone(
    client: httpx.AsyncClient,
    sessions: SessionFactory,
    database_url: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await add_user(sessions, "alice", Role.ADMIN)
    assert await login(client, "alice") == 200
    session_hash = sha256_hex(client.cookies.get(SESSION_COOKIE) or "")
    settings = settings_for(database_url)
    still_allowed = session_check(sessions, settings, TicketGrant(session_hash))
    assert await still_allowed() is True
    assert (await client.post(LOGOUT_PATH, headers=csrf_headers(client))).status_code == 204
    assert await still_allowed() is False
    monkeypatch.setattr(events, "PING_SECONDS", 0.1)
    frames = [frame async for frame in event_frames(settings, sessions, still_allowed)]
    assert frames == [CONNECTED_FRAME]
