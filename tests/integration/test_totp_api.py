from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from noc.auth.totp import counter_code, step_at
from noc.auth.users import create_user, enroll_totp
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuditEntry, AuthSession, User
from noc.db.session import SessionFactory, transaction

pytestmark = pytest.mark.integration

BASE_URL = "http://localhost"
PASSWORD = "correct horse battery"
LOGIN_PATH = "/api/auth/login"
ME_PATH = "/api/auth/me"
SETUP_PATH = "/api/auth/totp/setup"
ENABLE_PATH = "/api/auth/totp/enable"
DISABLE_PATH = "/api/auth/totp/disable"


def make_app(
    sessions: SessionFactory, database_url: str, required: list[Role] | None = None
) -> FastAPI:
    settings = Settings(
        database_url=database_url,
        api_token=SecretStr("test-token"),
        session_cookie_secure=False,
        totp_required_roles=required or [],
        _env_file=None,
    )
    application = create_app(settings)
    application.state.settings = settings
    application.state.sessions = sessions
    application.state.tickets = TicketStore()
    return application


def new_client(app: FastAPI) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)


@pytest.fixture
async def app(sessions: SessionFactory, database_url: str) -> FastAPI:
    return make_app(sessions, database_url)


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with new_client(app) as http:
        yield http


async def make_user(sessions: SessionFactory, name: str, role: Role = Role.OPERATOR) -> None:
    async with transaction(sessions) as session:
        await create_user(session, name, PASSWORD, role, "cli")


async def enrolled_secret(sessions: SessionFactory, name: str) -> str:
    async with transaction(sessions) as session:
        _, secret = await enroll_totp(session, name, "cli")
    return secret


def current_code(secret: str, offset_steps: int = 0) -> str:
    return counter_code(secret, step_at(utc_now()) + offset_steps)


async def login(
    http: httpx.AsyncClient, name: str, code: str | None = None, password: str = PASSWORD
) -> httpx.Response:
    body = {"username": name, "password": password}
    if code is not None:
        body["totp"] = code
    return await http.post(LOGIN_PATH, json=body)


def csrf(http: httpx.AsyncClient) -> dict[str, str]:
    return {CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""}


async def audit_reasons(sessions: SessionFactory) -> list[str]:
    async with sessions() as session:
        rows = await session.scalars(
            select(AuditEntry.payload).where(AuditEntry.action == "login_failed")
        )
        return [str(payload.get("reason", "")) for payload in rows]


async def test_a_user_without_totp_logs_in_as_before(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    response = await login(client, "alice")
    assert response.status_code == 200
    assert response.json()["totp_enabled"] is False


async def test_an_enrolled_user_needs_the_code(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    secret = await enrolled_secret(sessions, "alice")
    missing = await login(client, "alice")
    assert missing.status_code == 401
    assert missing.json() == {"detail": "authentication code required"}
    assert (await client.get(ME_PATH)).status_code == 401
    ok = await login(client, "alice", current_code(secret))
    assert ok.status_code == 200
    assert ok.json()["totp_enabled"] is True


async def test_a_wrong_code_is_refused_and_audited(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    secret = await enrolled_secret(sessions, "alice")
    wrong = "000000" if current_code(secret) != "000000" else "111111"
    response = await login(client, "alice", wrong)
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid authentication code"}
    assert "totp" in await audit_reasons(sessions)


async def test_a_code_cannot_be_used_twice(
    app: FastAPI, client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    secret = await enrolled_secret(sessions, "alice")
    code = current_code(secret)
    assert (await login(client, "alice", code)).status_code == 200
    async with new_client(app) as second:
        replay = await login(second, "alice", code)
    assert replay.status_code == 401
    assert replay.json() == {"detail": "invalid authentication code"}


async def test_a_wrong_password_never_reveals_that_totp_is_on(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    await enrolled_secret(sessions, "alice")
    response = await login(client, "alice", password="wrong horse battery")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid username or password"}


async def test_required_role_without_enrolment_cannot_log_in(
    sessions: SessionFactory, database_url: str
) -> None:
    await make_user(sessions, "ops", Role.OPERATOR)
    await make_user(sessions, "watcher", Role.VIEWER)
    app = make_app(sessions, database_url, required=[Role.OPERATOR, Role.ADMIN])
    async with new_client(app) as http:
        refused = await login(http, "ops")
        allowed = await login(http, "watcher")
    assert refused.status_code == 403
    assert "two-factor" in refused.json()["detail"]
    assert allowed.status_code == 200
    assert "totp_not_enrolled" in await audit_reasons(sessions)


async def test_self_service_setup_then_enable(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    await login(client, "alice")
    wrong_password = await client.post(
        SETUP_PATH, json={"current_password": "nope nope nope"}, headers=csrf(client)
    )
    assert wrong_password.status_code == 401
    setup = await client.post(SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client))
    assert setup.status_code == 200
    secret = setup.json()["secret"]
    assert setup.json()["uri"].startswith("otpauth://totp/")
    async with sessions() as session:
        user = await session.scalar(select(User).where(User.username == "alice"))
        assert user is not None
        assert user.totp_enabled is False
    bad = await client.post(ENABLE_PATH, json={"code": "000000"}, headers=csrf(client))
    assert bad.status_code == 422
    enabled = await client.post(
        ENABLE_PATH, json={"code": current_code(secret)}, headers=csrf(client)
    )
    assert enabled.status_code == 204
    me = await client.get(ME_PATH)
    assert me.json()["totp_enabled"] is True


async def test_enabling_ends_the_other_sessions(
    app: FastAPI, client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    await login(client, "alice")
    async with new_client(app) as other:
        await login(other, "alice")
        setup = await client.post(
            SETUP_PATH, json={"current_password": PASSWORD}, headers=csrf(client)
        )
        await client.post(
            ENABLE_PATH, json={"code": current_code(setup.json()["secret"])}, headers=csrf(client)
        )
        assert (await other.get(ME_PATH)).status_code == 401
    assert (await client.get(ME_PATH)).status_code == 200


async def test_disable_needs_password_and_a_fresh_code(
    app: FastAPI, client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    secret = await enrolled_secret(sessions, "alice")
    await login(client, "alice", current_code(secret))
    same_code = current_code(secret)
    reused = await client.post(
        DISABLE_PATH,
        json={"current_password": PASSWORD, "code": same_code},
        headers=csrf(client),
    )
    assert reused.status_code == 401
    next_code = current_code(secret, 1)
    disabled = await client.post(
        DISABLE_PATH,
        json={"current_password": PASSWORD, "code": next_code},
        headers=csrf(client),
    )
    assert disabled.status_code == 204
    async with new_client(app) as fresh:
        assert (await login(fresh, "alice")).status_code == 200


async def test_required_role_cannot_turn_totp_off(
    sessions: SessionFactory, database_url: str
) -> None:
    await make_user(sessions, "ops", Role.OPERATOR)
    secret = await enrolled_secret(sessions, "ops")
    app = make_app(sessions, database_url, required=[Role.OPERATOR])
    async with new_client(app) as http:
        await login(http, "ops", current_code(secret))
        response = await http.post(
            DISABLE_PATH,
            json={"current_password": PASSWORD, "code": current_code(secret, 1)},
            headers=csrf(http),
        )
    assert response.status_code == 403


async def test_totp_endpoints_need_a_session(client: httpx.AsyncClient) -> None:
    response = await client.post(SETUP_PATH, json={"current_password": PASSWORD})
    assert response.status_code == 401


async def test_clock_drift_of_one_step_still_logs_in(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    secret = await enrolled_secret(sessions, "alice")
    response = await login(client, "alice", current_code(secret, -1))
    assert response.status_code == 200


async def test_session_rows_are_created_only_after_the_second_factor(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await make_user(sessions, "alice")
    await enrolled_secret(sessions, "alice")
    await login(client, "alice")
    await login(client, "alice", "000000")
    async with sessions() as session:
        assert list(await session.scalars(select(AuthSession.id_hash))) == []
