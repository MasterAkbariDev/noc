import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import func, select

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.audit.chain import verify_chain
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from noc.auth.users import create_user, find_user
from noc.config import Settings
from noc.db.models import AuditEntry, AuthSession, User
from noc.db.session import SessionFactory, transaction

pytestmark = pytest.mark.integration

TOKEN = "test-token"
BASE_URL = "http://localhost"
ADMIN = "root-admin"
ADMIN_PASSWORD = "correct horse battery"
ALICE_PASSWORD = "alice horse battery"
NEW_PASSWORD = "another long password"
USERS_PATH = "/api/users"
LOGIN_PATH = "/api/auth/login"
ME_PATH = "/api/auth/me"
BEARER = {"Authorization": f"Bearer {TOKEN}"}
SELF_DISABLE = "an admin cannot disable their own account"
SELF_DEMOTE = "an admin cannot lower their own role"
RULE_TEXT = "password must be 12-128 characters"


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


async def login(http: httpx.AsyncClient, username: str, password: str) -> httpx.Response:
    return await http.post(LOGIN_PATH, json={"username": username, "password": password})


def csrf_headers(http: httpx.AsyncClient) -> dict[str, str]:
    return {CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""}


async def user_id_of(sessions: SessionFactory, username: str) -> uuid.UUID:
    async with sessions() as session:
        user = await find_user(session, username)
    assert user is not None
    return user.id


async def session_count(sessions: SessionFactory) -> int:
    async with sessions() as session:
        return int(await session.scalar(select(func.count()).select_from(AuthSession)) or 0)


async def audit_actors(sessions: SessionFactory, action: str) -> list[str]:
    async with sessions() as session:
        return list(
            await session.scalars(
                select(AuditEntry.actor).where(AuditEntry.action == action).order_by(AuditEntry.id)
            )
        )


@pytest.fixture
async def admin(app: FastAPI, sessions: SessionFactory) -> AsyncIterator[httpx.AsyncClient]:
    async with transaction(sessions) as session:
        await create_user(session, ADMIN, ADMIN_PASSWORD, Role.ADMIN, "cli")
    async with new_client(app) as http:
        assert (await login(http, ADMIN, ADMIN_PASSWORD)).status_code == 200
        yield http


@pytest.fixture
async def alice(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await create_user(session, "alice", ALICE_PASSWORD, Role.VIEWER, "cli")


@pytest.mark.usefixtures("alice")
async def test_list_shows_every_account_and_never_a_secret(
    admin: httpx.AsyncClient,
) -> None:
    response = await admin.get(USERS_PATH)
    assert response.status_code == 200
    rows = response.json()
    assert [row["username"] for row in rows] == ["alice", ADMIN]
    assert set(rows[0]) == {
        "id",
        "username",
        "role",
        "disabled",
        "created_at",
        "last_login_at",
    }
    assert rows[0]["role"] == "viewer"
    assert rows[0]["disabled"] is False
    assert rows[0]["last_login_at"] is None
    assert "password_hash" not in response.text


async def test_admin_creates_a_user_and_the_audit_names_the_admin(
    admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    response = await admin.post(
        USERS_PATH,
        json={"username": "Bob.Ops", "password": ALICE_PASSWORD, "role": "operator"},
        headers=csrf_headers(admin),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "bob.ops"
    assert body["role"] == "operator"
    assert body["disabled"] is False
    assert body["last_login_at"] is None
    assert await audit_actors(sessions, "user_created") == ["cli", ADMIN]
    assert ALICE_PASSWORD not in response.text


async def test_bearer_token_creates_a_user_as_the_api_token(
    app: FastAPI, sessions: SessionFactory
) -> None:
    async with new_client(app) as http:
        response = await http.post(
            USERS_PATH,
            json={"username": "carol", "password": ALICE_PASSWORD, "role": "viewer"},
            headers=BEARER,
        )
    assert response.status_code == 200
    assert await audit_actors(sessions, "user_created") == ["api-token"]


@pytest.mark.usefixtures("alice")
async def test_duplicate_username_is_a_conflict(admin: httpx.AsyncClient) -> None:
    response = await admin.post(
        USERS_PATH,
        json={"username": "ALICE", "password": NEW_PASSWORD, "role": "admin"},
        headers=csrf_headers(admin),
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "user alice already exists"}


async def test_weak_password_is_422_with_the_rule_text(
    admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    response = await admin.post(
        USERS_PATH,
        json={"username": "dave", "password": "short", "role": "viewer"},
        headers=csrf_headers(admin),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": RULE_TEXT}
    async with sessions() as session:
        assert await find_user(session, "dave") is None


async def test_bad_username_is_422_with_the_rule_text(admin: httpx.AsyncClient) -> None:
    response = await admin.post(
        USERS_PATH,
        json={"username": "A B!", "password": NEW_PASSWORD, "role": "viewer"},
        headers=csrf_headers(admin),
    )
    assert response.status_code == 422
    assert response.json()["detail"].startswith("username must be 3-32 characters")


@pytest.mark.usefixtures("alice")
async def test_role_change_applies_and_is_audited(
    admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    alice_id = await user_id_of(sessions, "alice")
    response = await admin.post(
        f"/api/users/{alice_id}/role", json={"role": "operator"}, headers=csrf_headers(admin)
    )
    assert response.status_code == 200
    assert response.json()["role"] == "operator"
    assert await audit_actors(sessions, "user_role_changed") == [ADMIN]


async def test_admin_cannot_demote_themselves(
    admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    admin_id = await user_id_of(sessions, ADMIN)
    response = await admin.post(
        f"/api/users/{admin_id}/role", json={"role": "viewer"}, headers=csrf_headers(admin)
    )
    assert response.status_code == 409
    assert response.json() == {"detail": SELF_DEMOTE}
    async with sessions() as session:
        stored = await find_user(session, ADMIN)
    assert stored is not None
    assert stored.role == "admin"


async def test_admin_cannot_disable_themselves(
    admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    admin_id = await user_id_of(sessions, ADMIN)
    response = await admin.post(f"/api/users/{admin_id}/disable", headers=csrf_headers(admin))
    assert response.status_code == 409
    assert response.json() == {"detail": SELF_DISABLE}
    assert (await admin.get(ME_PATH)).status_code == 200


@pytest.mark.usefixtures("alice")
async def test_disable_ends_the_target_session_at_once_and_enable_restores_login(
    app: FastAPI, admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    alice_id = await user_id_of(sessions, "alice")
    async with new_client(app) as alice_http:
        assert (await login(alice_http, "alice", ALICE_PASSWORD)).status_code == 200
        disabled = await admin.post(f"/api/users/{alice_id}/disable", headers=csrf_headers(admin))
        assert disabled.status_code == 200
        assert disabled.json()["disabled"] is True
        assert (await alice_http.get(ME_PATH)).status_code == 401
    assert await session_count(sessions) == 1
    async with new_client(app) as blocked:
        assert (await login(blocked, "alice", ALICE_PASSWORD)).status_code == 401
    enabled = await admin.post(f"/api/users/{alice_id}/enable", headers=csrf_headers(admin))
    assert enabled.status_code == 200
    assert enabled.json()["disabled"] is False
    async with new_client(app) as again:
        assert (await login(again, "alice", ALICE_PASSWORD)).status_code == 200
    assert await audit_actors(sessions, "user_disabled") == [ADMIN]
    assert await audit_actors(sessions, "user_enabled") == [ADMIN]


@pytest.mark.usefixtures("alice")
async def test_password_reset_ends_sessions_and_only_the_new_password_works(
    app: FastAPI, admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    alice_id = await user_id_of(sessions, "alice")
    async with new_client(app) as alice_http:
        assert (await login(alice_http, "alice", ALICE_PASSWORD)).status_code == 200
        reset = await admin.post(
            f"/api/users/{alice_id}/password",
            json={"new_password": NEW_PASSWORD},
            headers=csrf_headers(admin),
        )
        assert reset.status_code == 204
        assert (await alice_http.get(ME_PATH)).status_code == 401
    async with new_client(app) as old:
        assert (await login(old, "alice", ALICE_PASSWORD)).status_code == 401
    async with new_client(app) as new:
        assert (await login(new, "alice", NEW_PASSWORD)).status_code == 200
    assert await audit_actors(sessions, "user_password_reset") == [ADMIN]
    async with sessions() as session:
        assert await verify_chain(session) is None


@pytest.mark.usefixtures("alice")
async def test_password_reset_with_a_weak_password_is_422_with_the_rule_text(
    admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    alice_id = await user_id_of(sessions, "alice")
    response = await admin.post(
        f"/api/users/{alice_id}/password",
        json={"new_password": "short"},
        headers=csrf_headers(admin),
    )
    assert response.status_code == 422
    assert response.json() == {"detail": RULE_TEXT}
    assert await audit_actors(sessions, "user_password_reset") == []


async def test_unknown_user_id_is_404(admin: httpx.AsyncClient) -> None:
    missing = uuid.uuid4()
    for path, body in (
        (f"/api/users/{missing}/role", {"role": "viewer"}),
        (f"/api/users/{missing}/disable", None),
        (f"/api/users/{missing}/enable", None),
        (f"/api/users/{missing}/password", {"new_password": NEW_PASSWORD}),
    ):
        response = await admin.post(path, json=body, headers=csrf_headers(admin))
        assert response.status_code == 404, path
        assert response.json() == {"detail": "user not found"}


async def test_users_post_without_csrf_is_403(admin: httpx.AsyncClient) -> None:
    response = await admin.post(
        USERS_PATH,
        json={"username": "erin", "password": NEW_PASSWORD, "role": "viewer"},
    )
    assert response.status_code == 403


async def test_user_rows_are_not_touched_by_a_refused_create(
    admin: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    await admin.post(
        USERS_PATH,
        json={"username": "x", "password": NEW_PASSWORD, "role": "viewer"},
        headers=csrf_headers(admin),
    )
    async with sessions() as session:
        names = list(await session.scalars(select(User.username).order_by(User.username)))
    assert names == [ADMIN]
