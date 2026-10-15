import json
from collections.abc import Callable

import httpx
import pytest

from noc.scenarios.chaos_client import ChaosError, SentinelChaosClient
from tests.support.builders import KEY_ID, SECRET

BASE_URL = "https://demo-1:9443"
Handler = Callable[[httpx.Request], httpx.Response]


def client_with(handler: Handler) -> SentinelChaosClient:
    http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return SentinelChaosClient(BASE_URL, KEY_ID, SECRET, http)


def recording(
    seen: list[httpx.Request], reply: dict[str, object] | None = None, status: int = 200
) -> Handler:
    body = reply if reply is not None else {"active": True}

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=body)

    return handle


async def test_cpu_burn_start_posts_workers_and_ttl() -> None:
    seen: list[httpx.Request] = []
    client = client_with(recording(seen, {"active": True, "scenario": "cpu-burn"}))
    state = await client.start_cpu_burn(2, 900)

    [request] = seen
    assert request.method == "POST"
    assert request.url.path == "/v1/chaos/cpu-burn/start"
    assert json.loads(request.content) == {"workers": 2, "ttl_seconds": 900}
    assert state.active is True
    assert state.scenario == "cpu-burn"


async def test_cpu_burn_stop_posts_an_empty_body() -> None:
    seen: list[httpx.Request] = []
    await client_with(recording(seen, {"active": False})).stop_cpu_burn()

    [request] = seen
    assert request.url.path == "/v1/chaos/cpu-burn/stop"
    assert request.content == b"{}"


async def test_disk_fill_start_posts_target_and_ttl() -> None:
    seen: list[httpx.Request] = []
    await client_with(recording(seen)).start_disk_fill(92, 900)

    [request] = seen
    assert request.url.path == "/v1/chaos/disk-fill/start"
    assert json.loads(request.content) == {"target_percent": 92, "ttl_seconds": 900}


async def test_app_fault_start_posts_the_resource_fault_and_ttl() -> None:
    seen: list[httpx.Request] = []
    await client_with(recording(seen)).start_app_fault("svc:demo-shop", "memory_leak", 900)

    [request] = seen
    assert request.url.path == "/v1/chaos/app-fault/start"
    assert json.loads(request.content) == {
        "resource_id": "svc:demo-shop",
        "fault": "memory_leak",
        "ttl_seconds": 900,
    }


async def test_app_fault_stop_names_the_resource() -> None:
    seen: list[httpx.Request] = []
    await client_with(recording(seen, {"active": False})).stop_app_fault("svc:demo-shop")

    [request] = seen
    assert request.url.path == "/v1/chaos/app-fault/stop"
    assert json.loads(request.content) == {"resource_id": "svc:demo-shop"}


async def test_disk_fill_stop_posts_an_empty_body() -> None:
    seen: list[httpx.Request] = []
    await client_with(recording(seen, {"active": False})).stop_disk_fill()

    [request] = seen
    assert request.url.path == "/v1/chaos/disk-fill/stop"
    assert request.content == b"{}"


async def test_service_down_start_keeps_its_path_and_body() -> None:
    seen: list[httpx.Request] = []
    await client_with(recording(seen)).start_service_down("svc:demo-shop", 600)

    [request] = seen
    assert request.url.path == "/v1/chaos/service-down/start"
    assert json.loads(request.content) == {"resource_id": "svc:demo-shop", "ttl_seconds": 600}


async def test_sentinel_error_detail_becomes_the_chaos_error_code() -> None:
    seen: list[httpx.Request] = []
    client = client_with(recording(seen, {"detail": "NOT_ACTIVE"}, status=409))

    with pytest.raises(ChaosError) as caught:
        await client.stop_disk_fill()

    assert caught.value.code == "NOT_ACTIVE"


async def test_unreachable_sentinel_maps_to_unreachable() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    with pytest.raises(ChaosError) as caught:
        await client_with(refuse).start_cpu_burn(1, 900)

    assert caught.value.code == "UNREACHABLE"
