import uuid
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx
import pytest
from pydantic import SecretStr
from sqlalchemy import select

from noc.api.app import create_app
from noc.api.live_metrics import CPU_QUERY, SERVICE_MEMORY_QUERY, SERVICE_UP_QUERY, UPTIME_QUERY
from noc.api.prometheus import PrometheusReader
from noc.config import Settings
from noc.db.models import Target
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

TOKEN = "live-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
Handler = Callable[[httpx.Request], httpx.Response]

RANGES: dict[str, list[dict[str, Any]]] = {
    CPU_QUERY: [
        {"metric": {"target": "alpha-1"}, "values": [[100.0, "12.5"], [115.0, "NaN"]]},
        {"metric": {"target": "zeta-2"}, "values": [[100.0, "97"]]},
    ],
    SERVICE_MEMORY_QUERY: [
        {"metric": {"target": "alpha-1", "resource": "svc:shop"}, "values": [[100.0, "2048"]]}
    ],
}
INSTANTS: dict[str, list[dict[str, Any]]] = {
    UPTIME_QUERY: [{"metric": {"target": "alpha-1"}, "value": [100.0, "86400"]}],
    SERVICE_UP_QUERY: [
        {"metric": {"target": "alpha-1", "resource": "svc:shop"}, "value": [100.0, "1"]}
    ],
}


def answering_prometheus(seen: list[httpx.Request]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        query = request.url.params["query"]
        if request.url.path == "/api/v1/query_range":
            data = {"resultType": "matrix", "result": RANGES.get(query, [])}
        else:
            data = {"resultType": "vector", "result": INSTANTS.get(query, [])}
        return httpx.Response(200, json={"status": "success", "data": data})

    return handler


def unreachable(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("refused", request=request)


@asynccontextmanager
async def api_client(
    sessions: SessionFactory, prometheus: Handler
) -> AsyncIterator[httpx.AsyncClient]:
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
async def fleet(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        for name in ("zeta-2", "alpha-1"):
            await add_target(
                session, name, "10.0.0.2", f"https://{name}:9443", Environment.LAB, KEY_ID
            )


async def target_id(sessions: SessionFactory, name: str) -> uuid.UUID:
    async with transaction(sessions) as session:
        return (await session.scalars(select(Target.id).where(Target.name == name))).one()


@pytest.mark.usefixtures("fleet")
async def test_live_metrics_need_a_login(sessions: SessionFactory) -> None:
    async with api_client(sessions, answering_prometheus([])) as client:
        response = await client.get("/api/live/servers")
    assert response.status_code == 401


@pytest.mark.usefixtures("fleet")
async def test_the_fleet_view_lists_every_server_by_name_with_its_own_points(
    sessions: SessionFactory,
) -> None:
    seen: list[httpx.Request] = []
    async with api_client(sessions, answering_prometheus(seen)) as client:
        response = await client.get("/api/live/servers?range=15m", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["range"] == "15m"
    assert body["step_seconds"] == 15
    assert body["available"] is True
    assert [server["name"] for server in body["servers"]] == ["alpha-1", "zeta-2"]
    assert body["servers"][0]["cpu"] == [[100.0, 12.5]]
    assert body["servers"][1]["cpu"] == [[100.0, 97.0]]
    assert body["servers"][0]["net_in"] == []
    assert {request.url.params["step"] for request in seen} == {"15"}


@pytest.mark.usefixtures("fleet")
async def test_an_unknown_range_is_refused(sessions: SessionFactory) -> None:
    async with api_client(sessions, answering_prometheus([])) as client:
        response = await client.get("/api/live/servers?range=7d", headers=AUTH)
    assert response.status_code == 422


@pytest.mark.usefixtures("fleet")
async def test_one_server_has_its_uptime_and_services(sessions: SessionFactory) -> None:
    alpha = await target_id(sessions, "alpha-1")
    async with api_client(sessions, answering_prometheus([])) as client:
        response = await client.get(f"/api/live/servers/{alpha}?range=24h", headers=AUTH)
    assert response.status_code == 200
    body = response.json()
    assert body["step_seconds"] == 600
    assert body["uptime_seconds"] == 86400.0
    assert body["cpu"] == [[100.0, 12.5]]
    assert body["services"] == [
        {
            "resource_id": "svc:shop",
            "name": "shop",
            "up": True,
            "memory_bytes": [[100.0, 2048.0]],
            "memory_limit_bytes": None,
        }
    ]


@pytest.mark.usefixtures("fleet")
async def test_an_unknown_server_is_not_found(sessions: SessionFactory) -> None:
    async with api_client(sessions, answering_prometheus([])) as client:
        response = await client.get(f"/api/live/servers/{uuid.uuid4()}", headers=AUTH)
    assert response.status_code == 404


@pytest.mark.usefixtures("fleet")
async def test_an_unreachable_prometheus_says_not_available_instead_of_failing(
    sessions: SessionFactory,
) -> None:
    alpha = await target_id(sessions, "alpha-1")
    async with api_client(sessions, unreachable) as client:
        fleet_response = await client.get("/api/live/servers", headers=AUTH)
        server_response = await client.get(f"/api/live/servers/{alpha}", headers=AUTH)
    assert fleet_response.status_code == 200
    assert fleet_response.json()["available"] is False
    assert server_response.json()["available"] is False
    assert server_response.json()["uptime_seconds"] is None
