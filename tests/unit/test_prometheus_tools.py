import dataclasses
import json
import uuid
from collections.abc import Callable

import httpx
import pytest
from pydantic import BaseModel, ValidationError

from noc.tools.catalog import build_metric_tools
from noc.tools.prometheus_tools import (
    CATALOG,
    MAX_POINTS,
    PrometheusClient,
    QueryNamedMetricArgs,
    render_promql,
)
from noc.tools.recorder import MemoryToolCallRecorder
from noc.tools.registry import ToolRegistry
from noc.tools.spec import ToolContext, ToolOutput, ToolSpec
from noc_shared.tools import NoArgs
from tests.support.builders import tool_context

BASE_TIME = 1_700_000_000
Handler = Callable[[httpx.Request], httpx.Response]
CPU_QUERY = 'host:cpu_utilization:ratio_rate2m{target="demo-1"}'


class FakeResources:
    def __init__(self, resource_ids: frozenset[str]) -> None:
        self._resource_ids = resource_ids

    async def resource_ids(self, target_id: uuid.UUID) -> frozenset[str]:
        return self._resource_ids


def matrix(*series: dict[str, object]) -> dict[str, object]:
    return {"status": "success", "data": {"resultType": "matrix", "result": list(series)}}


def vector(*series: dict[str, object]) -> dict[str, object]:
    return {"status": "success", "data": {"resultType": "vector", "result": list(series)}}


def series(values: list[tuple[int, str]], **labels: str) -> dict[str, object]:
    return {"metric": labels, "values": [[timestamp, text] for timestamp, text in values]}


def instant(value: str, **labels: str) -> dict[str, object]:
    return {"metric": labels, "value": [BASE_TIME, value]}


def json_handler(payload: dict[str, object], status: int = 200) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=payload)

    return handler


def client_for(handler: Handler, calls: list[httpx.Request]) -> PrometheusClient:
    def record(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        return handler(request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(record))
    return PrometheusClient(http, "http://prometheus:9090/")


def context_for(name: str = "demo-1") -> ToolContext:
    base = tool_context()
    return dataclasses.replace(base, target=dataclasses.replace(base.target, name=name))


def named_args(**overrides: object) -> BaseModel:
    values: dict[str, object] = {"query": "cpu_usage", **overrides}
    return QueryNamedMetricArgs.model_validate(values)


def named_spec(client: PrometheusClient, resource_ids: frozenset[str] = frozenset()) -> ToolSpec:
    specs = build_metric_tools(client, FakeResources(resource_ids))
    return next(spec for spec in specs if spec.name == "query_named_metric")


async def run_named(
    handler: Handler,
    args: BaseModel,
    resource_ids: frozenset[str] = frozenset({"svc:demo-shop"}),
    context: ToolContext | None = None,
) -> tuple[ToolOutput, list[httpx.Request]]:
    calls: list[httpx.Request] = []
    spec = named_spec(client_for(handler, calls), resource_ids)
    output = await spec.handler(args, context or context_for())
    return output, calls


def test_catalog_entries_come_from_the_yaml() -> None:
    assert CATALOG["cpu_usage"] == 'host:cpu_utilization:ratio_rate2m{target="{target}"}'
    assert CATALOG["service_up"] == 'noc_service_up{target="{target}",resource="{resource}"}'


def test_unknown_query_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        QueryNamedMetricArgs.model_validate({"query": "drop_everything"})


def test_window_outside_the_allowed_set_is_rejected() -> None:
    with pytest.raises(ValidationError):
        QueryNamedMetricArgs.model_validate({"query": "cpu_usage", "window": "7d"})


def test_target_cannot_be_chosen_by_the_llm() -> None:
    with pytest.raises(ValidationError):
        QueryNamedMetricArgs.model_validate({"query": "cpu_usage", "target": "other-host"})


def test_label_injection_through_resource_id_is_impossible() -> None:
    with pytest.raises(ValidationError):
        QueryNamedMetricArgs.model_validate(
            {"query": "service_up", "resource_id": 'x"} or vector(1)'}
        )


def test_render_substitutes_only_the_given_values() -> None:
    rendered = render_promql(CATALOG["service_up"], "demo-1", "svc:demo-shop")
    assert rendered == 'noc_service_up{target="demo-1",resource="svc:demo-shop"}'


async def test_summary_has_min_max_avg_last_and_only_allowed_labels() -> None:
    payload = matrix(
        series(
            [(BASE_TIME, "0.2"), (BASE_TIME + 60, "0.4"), (BASE_TIME + 120, "0.6")],
            target="demo-1",
            instance="10.0.0.2:9100",
            job="node",
            mountpoint="/",
        )
    )
    output, calls = await run_named(json_handler(payload), named_args())
    assert output.ok
    assert output.data is not None
    summary = output.data["series"][0]
    assert summary["min"] == 0.2
    assert summary["max"] == 0.6
    assert summary["avg"] == pytest.approx(0.4)
    assert summary["last"] == 0.6
    assert summary["labels"] == {"target": "demo-1", "mountpoint": "/"}
    assert calls[0].url.path == "/api/v1/query_range"


async def test_query_uses_the_context_target_and_a_thirty_second_minimum_step() -> None:
    output, calls = await run_named(
        json_handler(matrix()), named_args(window="15m"), context=context_for("lab-7")
    )
    assert output.ok
    assert calls[0].url.params["query"] == 'host:cpu_utilization:ratio_rate2m{target="lab-7"}'
    assert calls[0].url.params["step"] == "30"
    assert output.data is not None
    assert output.data["step_seconds"] == 30


async def test_one_hour_window_uses_a_sixty_second_step() -> None:
    output, calls = await run_named(json_handler(matrix()), named_args(window="1h"))
    assert output.ok
    assert calls[0].url.params["step"] == "60"


async def test_long_series_is_downsampled_but_stats_use_every_point() -> None:
    points = [(BASE_TIME + index * 60, str(index)) for index in range(300)]
    output, _ = await run_named(
        json_handler(matrix(series(points, target="demo-1"))), named_args(window="6h")
    )
    assert output.ok
    assert output.data is not None
    summary = output.data["series"][0]
    assert len(summary["points"]) <= MAX_POINTS
    assert summary["min"] == 0
    assert summary["max"] == 299
    assert summary["last"] == 299


async def test_nan_points_and_empty_series_are_skipped() -> None:
    payload = matrix(
        series([(BASE_TIME, "NaN"), (BASE_TIME + 60, "0.5")], target="demo-1"),
        series([(BASE_TIME, "NaN")], target="demo-1", mountpoint="/data"),
    )
    output, _ = await run_named(json_handler(payload), named_args())
    assert output.data is not None
    assert len(output.data["series"]) == 1
    assert output.data["series"][0]["last"] == 0.5


async def test_resource_query_needs_a_registered_resource() -> None:
    output, calls = await run_named(
        json_handler(matrix()),
        named_args(query="service_up", resource_id="svc:other"),
    )
    assert not output.ok
    assert output.error == "resource_id is not registered for this target"
    assert calls == []


async def test_resource_query_with_a_registered_resource_is_sent() -> None:
    output, calls = await run_named(
        json_handler(matrix()),
        named_args(query="service_up", resource_id="svc:demo-shop"),
    )
    assert output.ok
    assert calls[0].url.params["query"] == (
        'noc_service_up{target="demo-1",resource="svc:demo-shop"}'
    )


async def test_resource_query_without_resource_id_is_refused() -> None:
    output, calls = await run_named(json_handler(matrix()), named_args(query="service_up"))
    assert not output.ok
    assert calls == []


async def test_host_query_refuses_a_resource_id() -> None:
    output, calls = await run_named(json_handler(matrix()), named_args(resource_id="svc:demo-shop"))
    assert not output.ok
    assert calls == []


async def test_invalid_target_name_is_refused_before_any_request() -> None:
    output, calls = await run_named(
        json_handler(matrix()), named_args(), context=context_for("a b")
    )
    assert not output.ok
    assert calls == []


async def test_prometheus_error_becomes_a_tool_error() -> None:
    error = {"status": "error", "errorType": "bad_data", "error": "parse error"}
    output, _ = await run_named(json_handler(error, status=400), named_args())
    assert not output.ok
    assert output.error == "prometheus: parse error"


async def test_transport_failure_becomes_a_tool_error() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    output, _ = await run_named(broken, named_args())
    assert not output.ok
    assert output.error is not None
    assert output.error.startswith("prometheus: ConnectError")


async def test_unreadable_body_becomes_a_tool_error() -> None:
    def gateway(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="<html>bad gateway</html>")

    output, _ = await run_named(gateway, named_args())
    assert not output.ok
    assert output.error == "prometheus: HTTP 502, unreadable body"


async def test_host_overview_makes_five_instant_queries_and_returns_a_flat_dict() -> None:
    answers: dict[str, dict[str, object]] = {
        CPU_QUERY: instant("0.73"),
        'host:cpu_pressure_waiting:ratio_rate5m{target="demo-1"}': instant("0.05"),
        'host:memory_available:ratio{target="demo-1"}': instant("0.41"),
        'host:memory_pressure_stalled:ratio_rate5m{target="demo-1"}': instant("0.0"),
    }
    fs_mounts = [instant("0.80", mountpoint="/"), instant("0.12", mountpoint="/data")]
    calls: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        query = request.url.params["query"]
        if query.startswith("host:fs_avail"):
            return httpx.Response(200, json=vector(*fs_mounts))
        return httpx.Response(200, json=vector(answers[query]))

    specs = build_metric_tools(client_for(handler, []), FakeResources(frozenset()))
    overview = next(spec for spec in specs if spec.name == "get_host_overview")
    output = await overview.handler(NoArgs(), context_for())

    assert len(calls) == 5
    assert calls[0].url.path == "/api/v1/query"
    assert output.ok
    assert output.data == {
        "target": "demo-1",
        "cpu_utilization": 0.73,
        "cpu_pressure_waiting": 0.05,
        "memory_available": 0.41,
        "memory_pressure_stalled": 0.0,
        "fs_avail_min": 0.12,
    }


async def test_host_overview_reports_missing_metrics_as_null() -> None:
    output, _ = await run_overview(json_handler(vector()))
    assert output.ok
    assert output.data is not None
    assert output.data["cpu_utilization"] is None
    assert output.data["fs_avail_min"] is None


async def test_host_overview_turns_prometheus_errors_into_tool_errors() -> None:
    output, _ = await run_overview(
        json_handler({"status": "error", "error": "unavailable"}, status=503)
    )
    assert not output.ok
    assert output.error == "prometheus: unavailable"


async def run_overview(handler: Handler) -> tuple[ToolOutput, list[httpx.Request]]:
    calls: list[httpx.Request] = []
    specs = build_metric_tools(client_for(handler, calls), FakeResources(frozenset()))
    overview = next(spec for spec in specs if spec.name == "get_host_overview")
    return await overview.handler(NoArgs(), context_for()), calls


async def test_registry_runs_the_tool_for_investigator_and_denies_others() -> None:
    payload = matrix(series([(BASE_TIME, "0.3")], target="demo-1"))
    specs = build_metric_tools(client_for(json_handler(payload), []), FakeResources(frozenset()))
    registry = ToolRegistry(specs, MemoryToolCallRecorder())
    arguments = json.dumps({"query": "cpu_usage", "window": "1h"})

    allowed = await registry.execute("query_named_metric", arguments, tool_context())
    denied = await registry.execute("query_named_metric", arguments, tool_context(agent="logs"))

    assert allowed.ok
    assert allowed.data is not None
    assert allowed.data["series"][0]["last"] == 0.3
    assert not denied.ok
    assert registry.names_for("investigator") == ["get_host_overview", "query_named_metric"]
    assert registry.names_for("logs") == []


async def test_registry_refuses_unknown_query_names_before_any_request() -> None:
    calls: list[httpx.Request] = []
    specs = build_metric_tools(
        client_for(json_handler(matrix()), calls), FakeResources(frozenset())
    )
    registry = ToolRegistry(specs, MemoryToolCallRecorder())
    result = await registry.execute(
        "query_named_metric", json.dumps({"query": "drop_everything"}), tool_context()
    )
    assert not result.ok
    assert calls == []
