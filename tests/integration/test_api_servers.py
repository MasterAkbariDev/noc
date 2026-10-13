import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import timedelta
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.prometheus import PrometheusReader
from noc.api.servers import CPU_QUERY, DISK_QUERY, MEMORY_QUERY, SERVICE_QUERY
from noc.config import Settings
from noc.db.base import utc_now
from noc.db.models import Incident, ManagedResourceRow, Target
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "servers-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
HIDDEN_FIELDS = ("sentinel_url", "address", "hmac_key_id")
BASE_TIME = 1_700_000_000
SCRAPED_AT = "2026-10-13T09:00:00+00:00"
ANSWERS: dict[str, list[tuple[dict[str, str], str]]] = {
    CPU_QUERY: [({"target": "alpha-1"}, "0.1"), ({"target": "zeta-2"}, "0.97")],
    MEMORY_QUERY: [({"target": "alpha-1"}, "0.4")],
    DISK_QUERY: [
        ({"target": "alpha-1", "mountpoint": "/"}, "0.3"),
        ({"target": "zeta-2", "mountpoint": "/"}, "0.5"),
        ({"target": "zeta-2", "mountpoint": "/var"}, "0.93"),
    ],
    SERVICE_QUERY: [({"target": "zeta-2", "resource": "ctr:db"}, "0")],
}


def scrape_body(name: str, job: str, health: str) -> dict[str, Any]:
    return {
        "labels": {"target": name, "job": job},
        "health": health,
        "lastScrape": SCRAPED_AT,
        "lastError": "",
    }


def targets_body() -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "activeTargets": [
                scrape_body("alpha-1", "node", "up"),
                scrape_body("alpha-1", "sentinel", "up"),
                scrape_body("zeta-2", "node", "down"),
                scrape_body("zeta-2", "sentinel", "up"),
            ],
            "droppedTargets": [],
        },
    }


def healthy_prometheus(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/api/v1/targets":
        return httpx.Response(200, json=targets_body())
    result = [
        {"metric": labels, "value": [BASE_TIME, value]}
        for labels, value in ANSWERS[request.url.params["query"]]
    ]
    data = {"resultType": "vector", "result": result}
    return httpx.Response(200, json={"status": "success", "data": data})


def prometheus_unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


@pytest.fixture
async def fleet(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        alpha = await add_target(
            session, "alpha-1", "10.0.0.2", "https://alpha-1:9443", Environment.LAB, KEY_ID
        )
        zeta = await add_target(
            session, "zeta-2", "10.0.0.9", "https://zeta-2:9443", Environment.LAB, KEY_ID
        )
        alpha.halted = True
        alpha.automation_level = "auto_safe"
        session.add(
            ManagedResourceRow(
                target_id=alpha.id,
                resource_id="svc:web",
                kind="systemd_unit",
                name="web",
                allowed_actions=["restart_service"],
            )
        )
        session.add(
            ManagedResourceRow(
                target_id=zeta.id,
                resource_id="ctr:db",
                kind="container",
                name="db",
                allowed_actions=[],
            )
        )
        session.add(
            ManagedResourceRow(
                target_id=zeta.id,
                resource_id="svc:api",
                kind="systemd_unit",
                name="api",
                allowed_actions=[],
            )
        )
        session.add(
            Incident(
                target_id=zeta.id,
                status="INVESTIGATING",
                severity="critical",
                title="CPUSaturated on zeta-2",
                trace_id="a" * 32,
            )
        )
        session.add(
            Incident(
                target_id=zeta.id,
                status="RESOLVED",
                severity="warning",
                title="DiskFillingFast on zeta-2",
                trace_id="b" * 32,
                opened_at=utc_now() - timedelta(days=1),
            )
        )


@asynccontextmanager
async def api_client(sessions: SessionFactory, prometheus: Any) -> AsyncIterator[httpx.AsyncClient]:
    settings = Settings(api_token=SecretStr(TOKEN), _env_file=None)
    app = create_app(settings)
    app.state.settings = settings
    app.state.sessions = sessions
    async with httpx.AsyncClient(transport=httpx.MockTransport(prometheus)) as prometheus_http:
        app.state.prometheus = PrometheusReader(prometheus_http, settings.prometheus_url)
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://noc"
        ) as client:
            yield client


@pytest.fixture
async def client(sessions: SessionFactory, fleet: None) -> AsyncIterator[httpx.AsyncClient]:
    async with api_client(sessions, healthy_prometheus) as http:
        yield http


async def test_servers_require_the_token(client: httpx.AsyncClient) -> None:
    assert (await client.get("/api/servers")).status_code == 401


async def test_servers_are_listed_by_name_with_status_metrics_and_headline(
    client: httpx.AsyncClient,
) -> None:
    response = await client.get("/api/servers", headers=AUTH)
    assert response.status_code == 200
    alpha, zeta = response.json()
    assert [alpha["name"], zeta["name"]] == ["alpha-1", "zeta-2"]
    assert alpha["status"] == "up"
    assert alpha["metrics"] == {
        "cpu_percent": 10.0,
        "memory_percent": 40.0,
        "disk_percent": 30.0,
        "disk_mount": "/",
    }
    assert alpha["automation_label"] == "Safe fixes run automatically"
    assert alpha["headline"] == "Halted — automation stopped"
    assert alpha["open_incidents"] == 0
    assert alpha["worst_severity"] is None
    assert zeta["status"] == "down"
    assert zeta["metrics"]["disk_mount"] == "/var"
    assert zeta["metrics"]["disk_percent"] == 93.0
    assert zeta["open_incidents"] == 1
    assert zeta["worst_severity"] == "critical"
    assert zeta["headline"] == "Not reachable · Disk 93% full · CPU 97% busy · 1 open incident"


async def test_server_detail_lists_resources_services_and_recent_incidents(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    zeta_id = await server_id(sessions, "zeta-2")
    response = await client.get(f"/api/servers/{zeta_id}", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert [resource["resource_id"] for resource in body["resources"]] == ["ctr:db", "svc:api"]
    assert body["services"] == [
        {"resource_id": "ctr:db", "name": "db", "up": False},
        {"resource_id": "svc:api", "name": "api", "up": None},
    ]
    assert [incident["title"] for incident in body["recent_incidents"]] == [
        "CPUSaturated on zeta-2",
        "DiskFillingFast on zeta-2",
    ]
    assert body["recent_incidents"][0]["target"] == "zeta-2"
    assert body["last_inventory_at"] is None


async def test_unknown_server_is_not_found(client: httpx.AsyncClient) -> None:
    response = await client.get(f"/api/servers/{uuid.uuid4()}", headers=AUTH)
    assert response.status_code == 404


async def test_server_responses_hide_addresses_and_keys(
    client: httpx.AsyncClient, sessions: SessionFactory
) -> None:
    zeta_id = await server_id(sessions, "zeta-2")
    listing = await client.get("/api/servers", headers=AUTH)
    detail = await client.get(f"/api/servers/{zeta_id}", headers=AUTH)
    for body in [*listing.json(), detail.json()]:
        for field in HIDDEN_FIELDS:
            assert field not in body
    for response in (listing, detail):
        assert "10.0.0.2" not in response.text
        assert "https://zeta-2:9443" not in response.text


async def test_an_unreachable_prometheus_shows_unknown_servers_not_an_error(
    sessions: SessionFactory, fleet: None
) -> None:
    async with api_client(sessions, prometheus_unreachable) as client:
        listing = await client.get("/api/servers", headers=AUTH)
        zeta_id = await server_id(sessions, "zeta-2")
        detail = await client.get(f"/api/servers/{zeta_id}", headers=AUTH)
    assert listing.status_code == 200
    alpha, zeta = listing.json()
    assert alpha["status"] == zeta["status"] == "unknown"
    assert alpha["metrics"] is None
    assert zeta["headline"] == "Status unknown · 1 open incident"
    assert detail.status_code == 200
    assert [service["up"] for service in detail.json()["services"]] == [None, None]


async def server_id(sessions: SessionFactory, name: str) -> uuid.UUID:
    async with sessions() as session:
        return (await session.scalars(select(Target.id).where(Target.name == name))).one()
