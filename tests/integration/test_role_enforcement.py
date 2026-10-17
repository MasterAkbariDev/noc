import uuid
from collections.abc import AsyncIterator, Iterator, Sequence
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from fastapi.dependencies.models import Dependant
from fastapi.dependencies.utils import get_dependant
from fastapi.routing import APIRoute
from pydantic import SecretStr
from sqlalchemy import select
from starlette.routing import BaseRoute

from noc.api.app import create_app
from noc.api.deps import current_principal
from noc.api.prometheus import PrometheusReader
from noc.api.tickets import TicketStore
from noc.audit.chain import verify_chain
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from noc.auth.users import create_user, find_user
from noc.config import Settings
from noc.db.models import AuditEntry, Incident
from noc.db.session import SessionFactory, transaction
from noc.detection.ingest import AlertIngestor
from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.policy.models import Environment
from noc.store.incidents import transition
from noc.store.targets import add_target
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration

TOKEN = "test-token"
BASE_URL = "http://localhost"
PASSWORD = "correct horse battery"
NEW_PASSWORD = "another long password"
NOTE = "restarted by hand after the leak fix"
LOGIN_PATH = "/api/auth/login"
FORBIDDEN = {"detail": "your role cannot do this"}
PUBLIC_API_ROUTES = {
    ("POST", "/api/auth/login"),
    ("POST", "/api/auth/logout"),
    ("GET", "/api/events/stream"),
    # Node-to-node routes: no session, each request is checked by its peer signature instead.
    ("POST", "/api/peer/hello"),
    ("GET", "/api/peer/status"),
}
READ_PATHS = [
    "/api/incidents",
    "/api/targets",
    "/api/servers",
    "/api/activity",
    "/api/system/health",
    "/api/system/llm",
]


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
    application.state.prometheus = PrometheusReader(
        httpx.AsyncClient(transport=httpx.MockTransport(prometheus_down)),
        settings.prometheus_url,
    )
    return application


def prometheus_down(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503)


async def signed_in(
    app: FastAPI, sessions: SessionFactory, username: str, role: Role
) -> httpx.AsyncClient:
    async with transaction(sessions) as session:
        await create_user(session, username, PASSWORD, role, "cli")
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL)
    response = await http.post(LOGIN_PATH, json={"username": username, "password": PASSWORD})
    assert response.status_code == 200
    return http


@pytest.fixture
async def clients(
    app: FastAPI, sessions: SessionFactory
) -> AsyncIterator[dict[Role, httpx.AsyncClient]]:
    opened: dict[Role, httpx.AsyncClient] = {}
    for role in Role:
        opened[role] = await signed_in(app, sessions, f"{role.value}-user", role)
    yield opened
    for http in opened.values():
        await http.aclose()


@pytest.fixture
async def escalated_incident(sessions: SessionFactory) -> uuid.UUID:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
    source = StaticAlertSource()
    source.alerts = [prometheus_alert()]
    await AlertIngestor(source, sessions, missing_polls_to_resolve=2).poll_once()
    async with sessions() as session:
        incident_id = (await session.scalars(select(Incident.id))).one()
    async with transaction(sessions) as session:
        incident = await session.get_one(Incident, incident_id)
        await transition(session, incident, IncidentStatus.INVESTIGATING, "test")
        await transition(
            session,
            incident,
            IncidentStatus.ESCALATED,
            "test",
            EscalationReason.UNKNOWN_ROOT_CAUSE,
        )
    return incident_id


async def create_target_user(sessions: SessionFactory) -> uuid.UUID:
    async with transaction(sessions) as session:
        user = await create_user(session, "target-user", PASSWORD, Role.VIEWER, "cli")
        return user.id


def csrf_headers(http: httpx.AsyncClient) -> dict[str, str]:
    return {CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""}


def user_requests(target: uuid.UUID) -> list[tuple[str, str, dict[str, str] | None, int]]:
    return [
        ("GET", "/api/users", None, 200),
        (
            "POST",
            "/api/users",
            {"username": "new-user", "password": PASSWORD, "role": "viewer"},
            200,
        ),
        ("POST", f"/api/users/{target}/role", {"role": "operator"}, 200),
        ("POST", f"/api/users/{target}/disable", None, 200),
        ("POST", f"/api/users/{target}/enable", None, 200),
        ("POST", f"/api/users/{target}/password", {"new_password": NEW_PASSWORD}, 204),
    ]


def reaches_principal(dependant: Dependant) -> bool:
    return any(
        item.call is current_principal or reaches_principal(item) for item in dependant.dependencies
    )


def api_routes(routes: Sequence[BaseRoute]) -> Iterator[tuple[APIRoute, bool]]:
    for route in routes:
        included: Any = getattr(route, "original_router", None)
        if included is None:
            if isinstance(route, APIRoute) and route.path.startswith("/api/"):
                yield route, False
            continue
        guarded_by_include = any(
            reaches_principal(get_dependant(path="", call=entry.dependency))
            for entry in route.include_context.dependencies
        )
        for child, guarded in api_routes(included.routes):
            yield child, guarded or guarded_by_include


def unguarded_api_routes(app: FastAPI) -> set[tuple[str, str]]:
    unguarded: set[tuple[str, str]] = set()
    for route, guarded in api_routes(app.routes):
        if not guarded and not reaches_principal(route.dependant):
            unguarded.update((method, route.path) for method in route.methods)
    return unguarded


def test_only_login_logout_stream_and_peer_routes_skip_the_principal(app: FastAPI) -> None:
    assert unguarded_api_routes(app) == PUBLIC_API_ROUTES


@pytest.mark.parametrize("path", READ_PATHS)
async def test_every_read_route_refuses_an_anonymous_caller(app: FastAPI, path: str) -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url=BASE_URL
    ) as anonymous:
        response = await anonymous.get(path)
    assert response.status_code == 401


@pytest.mark.parametrize("path", READ_PATHS)
@pytest.mark.parametrize("role", list(Role))
async def test_every_role_reads_every_read_route(
    clients: dict[Role, httpx.AsyncClient], path: str, role: Role
) -> None:
    response = await clients[role].get(path)
    assert response.status_code == 200, path


@pytest.mark.parametrize("role", [Role.VIEWER, Role.OPERATOR])
async def test_users_routes_are_admin_only(
    clients: dict[Role, httpx.AsyncClient], sessions: SessionFactory, role: Role
) -> None:
    target = await create_target_user(sessions)
    http = clients[role]
    for method, path, body, _ in user_requests(target):
        response = await http.request(method, path, json=body, headers=csrf_headers(http))
        assert response.status_code == 403, path
        assert response.json() == FORBIDDEN
    async with sessions() as session:
        stored = await find_user(session, "target-user")
    assert stored is not None
    assert stored.role == "viewer"
    assert stored.disabled is False


async def test_admin_can_use_every_users_route(
    clients: dict[Role, httpx.AsyncClient], sessions: SessionFactory
) -> None:
    target = await create_target_user(sessions)
    http = clients[Role.ADMIN]
    for method, path, body, expected in user_requests(target):
        response = await http.request(method, path, json=body, headers=csrf_headers(http))
        assert response.status_code == expected, path


async def test_viewer_cannot_close_an_escalated_incident(
    clients: dict[Role, httpx.AsyncClient],
    sessions: SessionFactory,
    escalated_incident: uuid.UUID,
) -> None:
    http = clients[Role.VIEWER]
    response = await http.post(
        f"/api/incidents/{escalated_incident}/close",
        headers=csrf_headers(http),
        json={"resolution_note": NOTE},
    )
    assert response.status_code == 403
    assert response.json() == FORBIDDEN
    async with sessions() as session:
        status = await session.scalar(select(Incident.status))
    assert status == "ESCALATED"


@pytest.mark.parametrize("role", [Role.OPERATOR, Role.ADMIN])
async def test_operator_and_admin_close_and_the_audit_names_them(
    clients: dict[Role, httpx.AsyncClient],
    sessions: SessionFactory,
    escalated_incident: uuid.UUID,
    role: Role,
) -> None:
    http = clients[role]
    response = await http.post(
        f"/api/incidents/{escalated_incident}/close",
        headers=csrf_headers(http),
        json={"resolution_note": NOTE},
    )
    assert response.status_code == 200
    assert response.json()["status"] == "CLOSED"
    async with sessions() as session:
        actor = await session.scalar(
            select(AuditEntry.actor).where(AuditEntry.action == "incident_closed")
        )
        assert await verify_chain(session) is None
    assert actor == f"{role.value}-user"


async def test_bearer_token_closes_as_the_api_token(
    app: FastAPI, sessions: SessionFactory, escalated_incident: uuid.UUID
) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url=BASE_URL) as http:
        response = await http.post(
            f"/api/incidents/{escalated_incident}/close",
            headers={"Authorization": f"Bearer {TOKEN}"},
            json={"resolution_note": NOTE},
        )
    assert response.status_code == 200
    async with sessions() as session:
        actor = await session.scalar(
            select(AuditEntry.actor).where(AuditEntry.action == "incident_closed")
        )
    assert actor == "api-token"


async def test_viewer_cannot_decide_on_an_action(
    clients: dict[Role, httpx.AsyncClient],
) -> None:
    http = clients[Role.VIEWER]
    response = await http.post(
        f"/api/incidents/{uuid.uuid4()}/actions/{uuid.uuid4()}/decision",
        headers=csrf_headers(http),
        json={"decision": "approved", "action_hash": "0" * 64},
    )
    assert response.status_code == 403
    assert response.json() == FORBIDDEN
