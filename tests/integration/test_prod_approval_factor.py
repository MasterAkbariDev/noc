import uuid
from collections.abc import AsyncIterator

import httpx
import pytest
from fastapi import FastAPI
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.tickets import TicketStore
from noc.auth.approval_factor import CODE_INVALID, CODE_REQUIRED, NEEDS_ENROLMENT, NEEDS_PERSON
from noc.auth.roles import Role
from noc.auth.sessions import CSRF_COOKIE, CSRF_HEADER
from noc.auth.totp import counter_code, step_at
from noc.auth.users import create_user, enroll_totp
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import AuditEntry, Incident
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "test-token"
PASSWORD = "correct horse battery"
HASH = "a" * 64


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


async def make_incident(sessions: SessionFactory, environment: Environment) -> uuid.UUID:
    name = f"{environment.value}-1"
    async with transaction(sessions) as session:
        target = await add_target(
            session, name, "10.0.0.2", f"https://{name}:9443", environment, KEY_ID
        )
        incident = Incident(
            target_id=target.id,
            status="AWAITING_APPROVAL",
            severity="critical",
            title="ServiceDown",
            trace_id="t" * 32,
        )
        session.add(incident)
        await session.flush()
        return incident.id


async def operator_client(
    app: FastAPI, sessions: SessionFactory, totp: bool
) -> tuple[httpx.AsyncClient, str | None]:
    secret = None
    async with transaction(sessions) as session:
        await create_user(session, "olivia", PASSWORD, Role.OPERATOR, "cli")
        if totp:
            _, secret = await enroll_totp(session, "olivia", "cli")
    http = httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://noc")
    body: dict[str, str] = {"username": "olivia", "password": PASSWORD}
    if secret is not None:
        body["totp"] = counter_code(secret, step_at(utc_now()) - 1)
    assert (await http.post("/api/auth/login", json=body)).status_code == 200
    return http, secret


async def decide(
    http: httpx.AsyncClient, incident_id: uuid.UUID, decision: str = "approved", **extra: str
) -> httpx.Response:
    return await http.post(
        f"/api/incidents/{incident_id}/actions/{uuid.uuid4()}/decision",
        json={"decision": decision, "action_hash": HASH, **extra},
        headers={CSRF_HEADER: http.cookies.get(CSRF_COOKIE) or ""},
    )


@pytest.fixture
async def enrolled(
    app: FastAPI, sessions: SessionFactory
) -> AsyncIterator[tuple[httpx.AsyncClient, str]]:
    http, secret = await operator_client(app, sessions, totp=True)
    assert secret is not None
    yield http, secret
    await http.aclose()


async def test_a_prod_approval_without_a_code_is_refused(
    sessions: SessionFactory, enrolled: tuple[httpx.AsyncClient, str]
) -> None:
    http, _ = enrolled
    incident_id = await make_incident(sessions, Environment.PROD)
    response = await decide(http, incident_id)
    assert response.status_code == 403
    assert response.json() == {"detail": CODE_REQUIRED}


async def test_a_fresh_code_passes_the_gate_and_cannot_be_reused(
    sessions: SessionFactory, enrolled: tuple[httpx.AsyncClient, str]
) -> None:
    http, secret = enrolled
    incident_id = await make_incident(sessions, Environment.PROD)
    code = counter_code(secret, step_at(utc_now()))
    passed = await decide(http, incident_id, totp=code)
    assert passed.status_code != 403
    replay = await decide(http, incident_id, totp=code)
    assert replay.status_code == 403
    assert replay.json() == {"detail": CODE_INVALID}
    async with sessions() as session:
        actions = list(await session.scalars(select(AuditEntry.action)))
    assert "approval_reauthenticated" in actions
    assert "approval_code_refused" in actions


async def test_lab_approvals_and_prod_rejections_need_no_code(
    sessions: SessionFactory, enrolled: tuple[httpx.AsyncClient, str]
) -> None:
    http, _ = enrolled
    lab = await make_incident(sessions, Environment.LAB)
    assert (await decide(http, lab)).status_code != 403
    prod = await make_incident(sessions, Environment.PROD)
    assert (await decide(http, prod, decision="rejected")).status_code != 403


async def test_an_operator_without_two_factor_cannot_approve_prod(
    app: FastAPI, sessions: SessionFactory
) -> None:
    http, _ = await operator_client(app, sessions, totp=False)
    incident_id = await make_incident(sessions, Environment.PROD)
    response = await decide(http, incident_id, totp="123456")
    await http.aclose()
    assert response.status_code == 403
    assert response.json() == {"detail": NEEDS_ENROLMENT}


async def test_the_api_token_cannot_approve_prod(app: FastAPI, sessions: SessionFactory) -> None:
    incident_id = await make_incident(sessions, Environment.PROD)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://noc"
    ) as http:
        response = await http.post(
            f"/api/incidents/{incident_id}/actions/{uuid.uuid4()}/decision",
            json={"decision": "approved", "action_hash": HASH, "totp": "123456"},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
    assert response.status_code == 403
    assert response.json() == {"detail": NEEDS_PERSON}


async def test_the_rule_can_be_switched_off(app: FastAPI, sessions: SessionFactory) -> None:
    app.state.settings = app.state.settings.model_copy(
        update={"prod_approval_requires_totp": False}
    )
    http, _ = await operator_client(app, sessions, totp=False)
    incident_id = await make_incident(sessions, Environment.PROD)
    response = await decide(http, incident_id)
    await http.aclose()
    assert response.status_code != 403
