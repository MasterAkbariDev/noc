from collections.abc import AsyncIterator
from datetime import timedelta
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import func, select, update

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.audit.chain import verify_chain
from noc.auth.login_limits import USERNAME_LIMIT
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER, SESSION_COOKIE, sha256_hex
from noc.auth.users import create_user, set_disabled
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuditEntry, AuthSession, LoginFailure, User
from noc.db.session import SessionFactory, transaction

pytestmark = pytest.mark.integration

TOKEN = "test-token"
BASE_URL = "http://localhost"
USERNAME = "alice"
PASSWORD = "correct horse battery"
NEW_PASSWORD = "another long password"
LOGIN_PATH = "/api/auth/login"
ME_PATH = "/api/auth/me"
LOGOUT_PATH = "/api/auth/logout"
PASSWORD_PATH = "/api/auth/password"
TICKET_PATH = "/api/events/ticket"
BEARER = {"Authorization": f"Bearer {TOKEN}"}


@pytest.fixture
async def app(sessions: SessionFactory, database_url: str) -> FastAPI:
    settings = Settings(
        database_url=database_url,
        api_token=SecretStr(TOKEN),
        session_cookie_secure=False,
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
async def client(app: FastAPI) -> AsyncIterator[httpx.AsyncClient]:
    async with new_client(app) as http:
        yield http


@pytest.fixture
async def alice(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await create_user(session, USERNAME, PASSWORD, Role.ADMIN, "cli")


async def login(
    http: httpx.AsyncClient, username: str = USERNAME, password: str = PASSWORD
) -> httpx.Response:
    return await http.post(LOGIN_PATH, json={"username": username, "password": password})


def csrf_headers(http: httpx.AsyncClient) -> dict[str, str]:
    return {CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""}


async def session_hashes(sessions: SessionFactory) -> list[str]:
    async with sessions() as session:
        return list(await session.scalars(select(AuthSession.id_hash)))


async def failure_count(sessions: SessionFactory) -> int:
    async with sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(LoginFailure)) or 0)


async def audit_rows(sessions: SessionFactory) -> list[tuple[str, str, dict[str, Any]]]:
    async with sessions() as session:
        result = await session.execute(
            select(AuditEntry.action, AuditEntry.subject, AuditEntry.payload).order_by(
                AuditEntry.id
            )
        )
        return [(row.action, row.subject, row.payload) for row in result]


@pytest.mark.usefixtures("alice")
async def test_login_sets_both_cookies_and_me_answers(client: httpx.AsyncClient) -> None:
    response = await login(client)
    assert response.status_code == 200
    assert response.json() == {"username": USERNAME, "role": "admin", "via": "session"}
    assert client.cookies.get(SESSION_COOKIE)
    assert client.cookies.get(CSRF_COOKIE)
    me = await client.get(ME_PATH)
    assert me.status_code == 200
    assert me.json() == {"username": USERNAME, "role": "admin", "via": "session"}


async def test_me_without_a_login_is_401(client: httpx.AsyncClient) -> None:
    response = await client.get(ME_PATH)
    assert response.status_code == 401


@pytest.mark.usefixtures("alice")
async def test_wrong_password_and_unknown_user_give_the_same_401(client: httpx.AsyncClient) -> None:
    wrong_password = await login(client, password="wrong horse battery")
    unknown_user = await login(client, username="ghost-user")
    assert wrong_password.status_code == 401
    assert unknown_user.status_code == 401
    assert (
        wrong_password.json() == unknown_user.json() == {"detail": "invalid username or password"}
    )


@pytest.mark.usefixtures("alice")
async def test_malformed_username_gets_the_same_401(client: httpx.AsyncClient) -> None:
    response = await login(client, username="A B!")
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid username or password"}


@pytest.mark.usefixtures("alice")
async def test_disabled_user_cannot_log_in_even_with_the_right_password(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "backup-admin", PASSWORD, Role.ADMIN, "cli")
        await set_disabled(session, USERNAME, True, "cli")
    response = await login(client)
    assert response.status_code == 401
    assert response.json() == {"detail": "invalid username or password"}


async def test_non_json_login_body_is_415(client: httpx.AsyncClient) -> None:
    response = await client.post(
        LOGIN_PATH,
        content=f"username={USERNAME}&password={PASSWORD}",
        headers={"content-type": "application/x-www-form-urlencoded"},
    )
    assert response.status_code == 415


@pytest.mark.usefixtures("alice")
async def test_sixth_failure_for_a_username_is_429_even_with_the_right_password(
    client: httpx.AsyncClient,
) -> None:
    for _ in range(USERNAME_LIMIT):
        assert (await login(client, password="wrong horse battery")).status_code == 401
    blocked = await login(client)
    assert blocked.status_code == 429
    assert blocked.json() == {"detail": "too many attempts, try again later"}
    assert blocked.headers["retry-after"] == "900"
    assert client.cookies.get(SESSION_COOKIE) is None


@pytest.mark.usefixtures("alice")
async def test_twenty_first_attempt_from_one_ip_is_429(client: httpx.AsyncClient) -> None:
    for number in range(20):
        response = await login(
            client, username=f"ghost{number:02d}", password="wrong horse battery"
        )
        assert response.status_code == 401
    blocked = await login(client)
    assert blocked.status_code == 429


@pytest.mark.usefixtures("alice")
async def test_a_disabled_ip_limit_keeps_shared_addresses_usable(app: FastAPI) -> None:
    app.state.settings = app.state.settings.model_copy(update={"login_ip_limit": 0})
    async with new_client(app) as http:
        for number in range(25):
            response = await login(http, username=f"ghost{number:02d}", password="wrong horse")
            assert response.status_code == 401
        assert (await login(http)).status_code == 200
        for _ in range(6):
            await login(http, username="ghost00", password="still wrong")
        assert (await login(http, username="ghost00")).status_code == 429


async def test_a_session_cookie_is_refused_without_csrf_and_accepted_with_it(
    client: httpx.AsyncClient, alice: None
) -> None:
    assert (await login(client)).status_code == 200
    missing = await client.post(TICKET_PATH)
    assert missing.status_code == 403
    assert missing.json() == {"detail": "csrf token missing or invalid"}
    wrong = await client.post(TICKET_PATH, headers={CSRF_HEADER: "not-the-token"})
    assert wrong.status_code == 403
    right = await client.post(TICKET_PATH, headers=csrf_headers(client))
    assert right.status_code == 200
    assert right.json()["ticket"]


async def test_bearer_token_needs_no_csrf(client: httpx.AsyncClient) -> None:
    response = await client.post(TICKET_PATH, headers=BEARER)
    assert response.status_code == 200


@pytest.mark.usefixtures("alice")
async def test_a_wrong_bearer_header_never_falls_back_to_the_cookie(
    client: httpx.AsyncClient,
) -> None:
    assert (await login(client)).status_code == 200
    response = await client.get(ME_PATH, headers={"Authorization": "Bearer wrong"})
    assert response.status_code == 401


async def test_bearer_token_is_an_admin_principal(client: httpx.AsyncClient) -> None:
    response = await client.get(ME_PATH, headers=BEARER)
    assert response.status_code == 200
    assert response.json() == {"username": "api-token", "role": "admin", "via": "token"}


@pytest.mark.usefixtures("alice")
async def test_idle_expiry_ends_the_session_and_removes_the_row(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    assert (await login(client)).status_code == 200
    async with transaction(sessions) as session:
        await session.execute(
            update(AuthSession).values(last_seen_at=utc_now() - timedelta(hours=2))
        )
    assert (await client.get(ME_PATH)).status_code == 401
    assert await session_hashes(sessions) == []


@pytest.mark.usefixtures("alice")
async def test_absolute_expiry_ends_the_session_and_removes_the_row(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    assert (await login(client)).status_code == 200
    async with transaction(sessions) as session:
        await session.execute(
            update(AuthSession).values(expires_at=utc_now() - timedelta(minutes=1))
        )
    assert (await client.get(ME_PATH)).status_code == 401
    assert await session_hashes(sessions) == []


@pytest.mark.usefixtures("alice")
async def test_logout_returns_204_clears_cookies_and_ends_the_session(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    assert (await login(client)).status_code == 200
    response = await client.post(LOGOUT_PATH, headers=csrf_headers(client))
    assert response.status_code == 204
    set_cookies = response.headers.get_list("set-cookie")
    assert len(set_cookies) == 2
    assert all("max-age=0" in cookie.lower() for cookie in set_cookies)
    assert await session_hashes(sessions) == []
    assert (await client.get(ME_PATH)).status_code == 401


@pytest.mark.usefixtures("alice")
async def test_login_while_holding_a_session_deletes_the_old_one(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    assert (await login(client)).status_code == 200
    old_token = client.cookies.get(SESSION_COOKIE)
    assert old_token is not None
    assert (await login(client)).status_code == 200
    hashes = await session_hashes(sessions)
    assert len(hashes) == 1
    assert sha256_hex(old_token) not in hashes


@pytest.mark.usefixtures("alice")
async def test_password_change_keeps_this_session_and_ends_the_others(
    app: FastAPI, client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    assert (await login(client)).status_code == 200
    async with new_client(app) as other:
        assert (await login(other)).status_code == 200
        wrong = await client.post(
            PASSWORD_PATH,
            json={"current_password": "wrong horse battery", "new_password": NEW_PASSWORD},
            headers=csrf_headers(client),
        )
        assert wrong.status_code == 401
        assert await failure_count(sessions) == 1
        changed = await client.post(
            PASSWORD_PATH,
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=csrf_headers(client),
        )
        assert changed.status_code == 204
        assert (await other.get(ME_PATH)).status_code == 401
        assert (await client.get(ME_PATH)).status_code == 200
    assert len(await session_hashes(sessions)) == 1


@pytest.mark.usefixtures("alice")
async def test_password_change_with_the_bearer_token_is_400(client: httpx.AsyncClient) -> None:
    response = await client.post(
        PASSWORD_PATH,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=BEARER,
    )
    assert response.status_code == 400


@pytest.mark.usefixtures("alice")
async def test_password_change_rejects_a_weak_new_password(client: httpx.AsyncClient) -> None:
    assert (await login(client)).status_code == 200
    response = await client.post(
        PASSWORD_PATH,
        json={"current_password": PASSWORD, "new_password": "short"},
        headers=csrf_headers(client),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": "password must be 12-128 characters"}


@pytest.mark.usefixtures("alice")
async def test_role_change_in_the_database_applies_on_the_next_request(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    assert (await login(client)).status_code == 200
    async with transaction(sessions) as session:
        await session.execute(update(User).where(User.username == USERNAME).values(role="viewer"))
    response = await client.get(ME_PATH)
    assert response.json()["role"] == "viewer"


@pytest.mark.usefixtures("alice")
async def test_disabling_a_user_ends_their_session_at_once(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    assert (await login(client)).status_code == 200
    async with transaction(sessions) as session:
        await create_user(session, "backup-admin", PASSWORD, Role.ADMIN, "cli")
        await set_disabled(session, USERNAME, True, "cli")
    assert (await client.get(ME_PATH)).status_code == 401
    assert await session_hashes(sessions) == []


@pytest.mark.usefixtures("alice")
async def test_audit_records_auth_events_without_any_secret(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await login(client, password="wrong horse battery")
    assert (await login(client)).status_code == 200
    changed = await client.post(
        PASSWORD_PATH,
        json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
        headers=csrf_headers(client),
    )
    assert changed.status_code == 204
    assert (await client.post(LOGOUT_PATH, headers=csrf_headers(client))).status_code == 204
    rows = await audit_rows(sessions)
    assert [action for action, _, _ in rows] == [
        "user_created",
        "login_failed",
        "login",
        "password_changed",
        "logout",
    ]
    async with sessions() as session:
        assert await verify_chain(session) is None
        stored_hash = await session.scalar(select(User.password_hash))
    recorded = repr(rows)
    for secret in (PASSWORD, NEW_PASSWORD, stored_hash):
        assert secret not in recorded
    assert await session_hashes(sessions) == []


async def test_a_failed_login_is_audited_as_anonymous(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await login(client, username="mallory-typed-this")
    async with sessions() as session:
        entry = await session.scalar(select(AuditEntry).where(AuditEntry.action == "login_failed"))
    assert entry is not None
    assert entry.actor == "anonymous"
    assert entry.subject == "user:mallory-typed-this"


async def test_an_oversized_password_is_refused_before_hashing(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    response = await login(client, password="x" * 100_000)
    assert response.status_code == 422
    assert await failure_count(sessions) == 0
