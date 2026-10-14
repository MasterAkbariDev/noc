from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.app import create_app
from noc.api.prometheus import PrometheusReader
from noc.audit.chain import append_audit
from noc.auth.roles import Role
from noc.auth.users import create_user
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import Incident, Target, WorkerHeartbeat
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.incidents import add_event
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "overview-token"
BASE_URL = "http://localhost"
OVERVIEW_PATH = "/api/overview"
LOGIN_PATH = "/api/auth/login"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
VIEWER_NAME = "vic"
VIEWER_PASSWORD = "correct horse battery"
ZETA_TITLE = "Disk almost full on zeta-2"
ALPHA_TITLE = "CPU busy on alpha-1"
ESCALATED_HEADLINE = (
    "Disk almost full on zeta-2 needs you: automatic actions are switched off on this server."
)
ESCALATED_ADVICE = "Fix it by hand, then close the incident with a note."
SCRAPED_AT = "2026-10-13T09:00:00+00:00"
Reader = Callable[[httpx.Request], httpx.Response]


def targets_body(zeta_health: str) -> dict[str, Any]:
    healths = {"alpha-1": "up", "zeta-2": zeta_health}
    active = [
        {
            "labels": {"target": name, "job": "node"},
            "health": health,
            "lastScrape": SCRAPED_AT,
            "lastError": "",
        }
        for name, health in healths.items()
    ]
    return {"status": "success", "data": {"activeTargets": active, "droppedTargets": []}}


def prometheus_with(zeta_health: str) -> Reader:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/targets":
            return httpx.Response(200, json=targets_body(zeta_health))
        empty = {"resultType": "vector", "result": []}
        return httpx.Response(200, json={"status": "success", "data": empty})

    return handler


def prometheus_unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


ZETA_UP = prometheus_with("up")
ZETA_DOWN = prometheus_with("down")


def make_settings(**overrides: Any) -> Settings:
    return Settings(api_token=SecretStr(TOKEN), _env_file=None, **overrides)


@pytest.fixture(autouse=True)
def no_egress_proxies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOC_GEMINI_PROXY", raising=False)
    monkeypatch.delenv("NOC_GROQ_PROXY", raising=False)


@asynccontextmanager
async def api_client(
    sessions: SessionFactory, settings: Settings, prometheus: Reader
) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(transport=httpx.MockTransport(prometheus)) as prometheus_http:
        app.state.prometheus = PrometheusReader(prometheus_http, settings.prometheus_url)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url=BASE_URL
        ) as client:
            yield client


async def add_fleet(session: AsyncSession) -> tuple[Target, Target]:
    alpha = await add_target(
        session, "alpha-1", "10.0.0.2", "https://alpha-1:9443", Environment.LAB, KEY_ID
    )
    zeta = await add_target(
        session, "zeta-2", "10.0.0.9", "https://zeta-2:9443", Environment.LAB, KEY_ID
    )
    return alpha, zeta


@pytest.fixture
async def heartbeat(sessions: SessionFactory) -> None:
    now = utc_now()
    async with transaction(sessions) as session:
        session.add(
            WorkerHeartbeat(
                worker_id="worker-1",
                started_at=now,
                last_beat_at=now,
                last_poll_ok_at=now,
                version="dev",
            )
        )


@pytest.fixture
async def quiet_fleet(sessions: SessionFactory, heartbeat: None) -> None:
    async with transaction(sessions) as session:
        await add_fleet(session)


@pytest.fixture
async def fleet(sessions: SessionFactory, heartbeat: None) -> None:
    now = utc_now()
    async with transaction(sessions) as session:
        alpha, zeta = await add_fleet(session)
        escalated = Incident(
            target_id=zeta.id,
            status="ESCALATED",
            severity="critical",
            title=ZETA_TITLE,
            trace_id="a" * 32,
            opened_at=now - timedelta(hours=3),
            escalated_at=now - timedelta(hours=2),
            escalation_reason="execution_not_available",
        )
        waiting = Incident(
            target_id=alpha.id,
            status="AWAITING_APPROVAL",
            severity="warning",
            title=ALPHA_TITLE,
            trace_id="b" * 32,
            opened_at=now - timedelta(minutes=90),
            plan_at=now - timedelta(hours=1),
        )
        resolved = Incident(
            target_id=alpha.id,
            status="RESOLVED",
            severity="info",
            title="Old blip on alpha-1",
            trace_id="c" * 32,
            opened_at=now - timedelta(days=1),
            resolved_at=now - timedelta(days=1),
        )
        session.add_all([escalated, waiting, resolved])
        await session.flush()
        await add_event(
            session,
            escalated.id,
            "state_changed",
            "supervisor",
            {"from": "DIAGNOSED", "to": "ESCALATED", "reason": "execution_not_available"},
        )
        await append_audit(session, "alice", "login", "alice", {})


@pytest.fixture
async def viewer(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await create_user(session, VIEWER_NAME, VIEWER_PASSWORD, Role.VIEWER, "cli")


async def fetch_overview(client: httpx.AsyncClient) -> dict[str, Any]:
    response = await client.get(OVERVIEW_PATH, headers=AUTH)
    assert response.status_code == 200
    body: dict[str, Any] = response.json()
    return body


async def test_overview_requires_a_login(sessions: SessionFactory, quiet_fleet: None) -> None:
    async with api_client(sessions, make_settings(), ZETA_UP) as client:
        response = await client.get(OVERVIEW_PATH)
    assert response.status_code == 401


@pytest.mark.usefixtures("viewer")
async def test_a_viewer_session_can_read_the_overview(
    sessions: SessionFactory, quiet_fleet: None
) -> None:
    settings = make_settings(session_cookie_secure=False)
    async with api_client(sessions, settings, ZETA_UP) as client:
        login = await client.post(
            LOGIN_PATH, json={"username": VIEWER_NAME, "password": VIEWER_PASSWORD}
        )
        assert login.status_code == 200
        response = await client.get(OVERVIEW_PATH)
    assert response.status_code == 200
    assert response.json()["verdict"]["level"] == "ok"


@pytest.mark.usefixtures("fleet")
async def test_incidents_that_need_a_person_are_listed_oldest_first_with_the_headline(
    sessions: SessionFactory,
) -> None:
    async with api_client(sessions, make_settings(), ZETA_DOWN) as client:
        body = await fetch_overview(client)
    titles = [item["title"] for item in body["needs_attention"]]
    assert titles == [ZETA_TITLE, ALPHA_TITLE]
    first = body["needs_attention"][0]
    assert first["target"] == "zeta-2"
    assert first["status_label"] == "Needs you"
    assert first["summary"] == ESCALATED_HEADLINE
    assert first["advice"] == ESCALATED_ADVICE
    assert body["needs_attention"][1]["summary"] == f"{ALPHA_TITLE}: waiting for approval."


@pytest.mark.usefixtures("fleet")
async def test_kpis_count_open_incidents_and_servers(sessions: SessionFactory) -> None:
    async with api_client(sessions, make_settings(), ZETA_DOWN) as client:
        body = await fetch_overview(client)
    kpis = body["kpis"]
    assert kpis["open_incidents"] == 2
    assert kpis["needs_you"] == 2
    assert kpis["servers_up"] == 1
    assert kpis["servers_total"] == 2
    assert kpis["llm_keys_ok"] == kpis["llm_keys_total"]
    assert [server["name"] for server in body["servers"]] == ["alpha-1", "zeta-2"]


@pytest.mark.usefixtures("fleet")
async def test_the_verdict_asks_for_attention_when_incidents_need_a_person(
    sessions: SessionFactory,
) -> None:
    async with api_client(sessions, make_settings(), ZETA_DOWN) as client:
        body = await fetch_overview(client)
    assert body["verdict"] == {"level": "attention", "sentence": "2 incidents need you"}


@pytest.mark.usefixtures("fleet")
async def test_activity_merges_incident_events_and_audit_newest_first(
    sessions: SessionFactory,
) -> None:
    async with api_client(sessions, make_settings(), ZETA_DOWN) as client:
        body = await fetch_overview(client)
    activity = body["activity"]
    assert activity[0]["kind"] == "audit"
    assert activity[0]["text"] == "alice signed in"
    incident_items = [item for item in activity if item["kind"] == "incident"]
    assert incident_items[0]["text"] == f"{ZETA_TITLE}: Needs you"
    assert incident_items[0]["incident_id"] is not None
    timestamps = [datetime.fromisoformat(item["ts"]) for item in activity]
    assert timestamps == sorted(timestamps, reverse=True)


async def test_activity_is_capped_at_fifteen_entries(
    sessions: SessionFactory, quiet_fleet: None
) -> None:
    async with transaction(sessions) as session:
        for number in range(20):
            await append_audit(session, "cli", "target_added", f"lab-{number}", {"env": "lab"})
    async with api_client(sessions, make_settings(), ZETA_UP) as client:
        body = await fetch_overview(client)
    assert len(body["activity"]) == 15
    assert body["activity"][0]["text"] == "cli added the target lab-19"


async def test_a_quiet_fleet_is_all_systems_operational(
    sessions: SessionFactory, quiet_fleet: None
) -> None:
    async with api_client(sessions, make_settings(), ZETA_UP) as client:
        body = await fetch_overview(client)
    assert body["verdict"] == {"level": "ok", "sentence": "All systems operational"}
    assert body["needs_attention"] == []
    assert body["kpis"]["open_incidents"] == 0


async def test_an_unreachable_prometheus_degrades_the_verdict_without_a_500(
    sessions: SessionFactory, quiet_fleet: None
) -> None:
    async with api_client(sessions, make_settings(), prometheus_unreachable) as client:
        response = await client.get(OVERVIEW_PATH, headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["verdict"] == {
        "level": "degraded",
        "sentence": "Prometheus: Prometheus cannot be reached",
    }
    assert [server["status"] for server in body["servers"]] == ["unknown", "unknown"]
    assert all(server["metrics"] is None for server in body["servers"])
