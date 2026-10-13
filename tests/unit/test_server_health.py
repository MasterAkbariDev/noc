import math
import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest

from noc.api.prometheus import PrometheusReader, Sample, ScrapeTarget
from noc.api.schemas import ServerMetrics, ServerStatus, ServiceState
from noc.api.servers import (
    CPU_QUERY,
    DISK_QUERY,
    MEMORY_QUERY,
    SERVICE_QUERY,
    FleetReadings,
    headline,
    metrics_for,
    read_fleet,
    scrape_status,
    server_summary,
    service_states,
)
from noc.db.models import Incident, ManagedResourceRow, Target

BASE_TIME = 1_700_000_000
SCRAPED_AT = "2026-10-13T09:00:00+00:00"
Handler = Callable[[httpx.Request], httpx.Response]
HEALTHY = ServerMetrics(cpu_percent=12.0, memory_percent=40.0, disk_percent=40.0, disk_mount="/")


def server(name: str = "demo-1", halted: bool = False, level: str = "auto_safe") -> Target:
    return Target(
        id=uuid.uuid4(),
        name=name,
        address="10.0.0.2",
        sentinel_url="https://demo-1:9443",
        environment="lab",
        automation_level=level,
        hmac_key_id="noc-test-key",
        halted=halted,
    )


def open_incident(severity: str = "warning") -> Incident:
    return Incident(
        target_id=uuid.uuid4(),
        status="INVESTIGATING",
        severity=severity,
        title="HostCPUSaturated on demo-1",
        trace_id="0" * 32,
    )


def scrape_body(name: str, health: str = "up", job: str = "node") -> dict[str, Any]:
    return {
        "labels": {"target": name, "job": job},
        "health": health,
        "lastScrape": SCRAPED_AT,
        "lastError": "",
    }


def scrape(name: str, health: str = "up", job: str = "node") -> ScrapeTarget:
    return ScrapeTarget.model_validate(scrape_body(name, health, job))


def sample(value: float, **labels: str) -> Sample:
    return Sample(labels=labels, value=value)


def readings(
    scrape_targets: list[ScrapeTarget] | None = None,
    cpu: list[Sample] | None = None,
    memory: list[Sample] | None = None,
    disk: list[Sample] | None = None,
    services: list[Sample] | None = None,
) -> FleetReadings:
    return FleetReadings(
        scrape_targets=scrape_targets,
        cpu=cpu,
        memory=memory,
        disk=disk,
        services=services,
    )


def vector_body(*samples: Sample) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [
                {"metric": item.labels, "value": [BASE_TIME, str(item.value)]} for item in samples
            ],
        },
    }


def fake_prometheus(answers: dict[str, list[Sample]], calls: list[str]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/targets":
            body = {
                "status": "success",
                "data": {
                    "activeTargets": [
                        scrape_body("demo-1", job="node"),
                        scrape_body("demo-1", job="sentinel"),
                    ],
                    "droppedTargets": [],
                },
            }
            return httpx.Response(200, json=body)
        query = request.url.params["query"]
        calls.append(query)
        return httpx.Response(200, json=vector_body(*answers.get(query, [])))

    return handler


def failing(status: int | None) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        if status is None:
            raise httpx.ConnectError("refused", request=request)
        if status == 200:
            return httpx.Response(200, text="not json")
        return httpx.Response(status, json={"status": "error"})

    return handler


def test_cpu_memory_and_the_fullest_mount_become_percentages() -> None:
    fleet = readings(
        cpu=[sample(0.375, target="demo-1")],
        memory=[sample(0.6, target="demo-1")],
        disk=[
            sample(0.4, target="demo-1", mountpoint="/"),
            sample(0.92, target="demo-1", mountpoint="/data"),
        ],
    )
    assert metrics_for("demo-1", fleet) == ServerMetrics(
        cpu_percent=37.5, memory_percent=60.0, disk_percent=92.0, disk_mount="/data"
    )


def test_samples_of_other_targets_are_not_used() -> None:
    fleet = readings(cpu=[sample(0.5, target="other-2")])
    assert metrics_for("demo-1", fleet) is None


@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_a_non_finite_reading_is_dropped_instead_of_breaking_the_json(value: float) -> None:
    fleet = readings(disk=[sample(value, target="demo-1", mountpoint="/")])
    assert metrics_for("demo-1", fleet) is None


def test_status_is_up_when_every_scrape_target_of_the_server_is_up() -> None:
    fleet = [scrape("demo-1", job="node"), scrape("demo-1", job="sentinel")]
    status, last = scrape_status(fleet, "demo-1")
    assert status == "up"
    assert last == datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def test_one_down_scrape_target_makes_the_server_down() -> None:
    fleet = [scrape("demo-1", job="node"), scrape("demo-1", "down", job="sentinel")]
    assert scrape_status(fleet, "demo-1")[0] == "down"


def test_a_server_without_scrape_targets_is_unknown() -> None:
    fleet = [scrape("other-2")]
    assert scrape_status(fleet, "demo-1") == ("unknown", None)


def test_an_unreachable_prometheus_gives_unknown_status_and_no_metrics() -> None:
    summary = server_summary(server(), readings(), [])
    assert summary.status == "unknown"
    assert summary.metrics is None
    assert summary.last_scrape_at is None
    assert summary.headline == "Status unknown"


@pytest.mark.parametrize(
    ("status", "halted", "metrics", "open_count", "expected"),
    [
        ("up", False, HEALTHY, 0, "Healthy"),
        ("down", False, None, 0, "Not reachable"),
        ("unknown", False, None, 0, "Status unknown"),
        ("up", True, HEALTHY, 0, "Halted — automation stopped"),
        (
            "up",
            False,
            ServerMetrics(cpu_percent=5.0, memory_percent=5.0, disk_percent=92.0, disk_mount="/"),
            1,
            "Disk 92% full · 1 open incident",
        ),
        ("up", False, HEALTHY, 2, "2 open incidents"),
        (
            "up",
            False,
            ServerMetrics(cpu_percent=95.0, memory_percent=91.0, disk_percent=10.0, disk_mount="/"),
            0,
            "Memory 91% used · CPU 95% busy",
        ),
    ],
)
def test_headline_names_the_problem_in_plain_words(
    status: ServerStatus,
    halted: bool,
    metrics: ServerMetrics | None,
    open_count: int,
    expected: str,
) -> None:
    assert headline(status, halted, metrics, open_count) == expected


def test_summary_counts_open_incidents_and_keeps_the_worst_severity() -> None:
    incidents = [open_incident("warning"), open_incident("critical")]
    summary = server_summary(server(), readings(), incidents)
    assert summary.open_incidents == 2
    assert summary.worst_severity == "critical"


def test_summary_without_incidents_has_no_severity() -> None:
    summary = server_summary(server(), readings(), [])
    assert summary.open_incidents == 0
    assert summary.worst_severity is None


def test_automation_label_comes_from_the_plain_language_table() -> None:
    summary = server_summary(server(level="approval_required"), readings(), [])
    assert summary.automation_label == "Fixes need approval"


def test_summary_never_carries_address_sentinel_url_or_key_id() -> None:
    summary = server_summary(server(), readings(), [])
    dumped = summary.model_dump_json()
    for secret in ("10.0.0.2", "https://demo-1:9443", "noc-test-key"):
        assert secret not in dumped


def test_only_service_kinds_get_a_service_state() -> None:
    resources = [
        ManagedResourceRow(
            target_id=uuid.uuid4(),
            resource_id="svc:web",
            kind="systemd_unit",
            name="web",
            allowed_actions=[],
        ),
        ManagedResourceRow(
            target_id=uuid.uuid4(),
            resource_id="log:nginx",
            kind="log_source",
            name="nginx",
            allowed_actions=[],
        ),
    ]
    services = [sample(1.0, target="demo-1", resource="svc:web")]
    assert service_states(resources, services, "demo-1") == [
        ServiceState(resource_id="svc:web", name="web", up=True)
    ]


def test_a_stopped_service_is_down_and_a_missing_one_is_unknown() -> None:
    resources = [
        ManagedResourceRow(
            target_id=uuid.uuid4(),
            resource_id="ctr:db",
            kind="container",
            name="db",
            allowed_actions=[],
        ),
        ManagedResourceRow(
            target_id=uuid.uuid4(),
            resource_id="svc:web",
            kind="systemd_unit",
            name="web",
            allowed_actions=[],
        ),
    ]
    services = [sample(0.0, target="demo-1", resource="ctr:db")]
    assert service_states(resources, services, "demo-1") == [
        ServiceState(resource_id="ctr:db", name="db", up=False),
        ServiceState(resource_id="svc:web", name="web", up=None),
    ]


async def test_each_metric_is_asked_once_for_the_whole_fleet() -> None:
    calls: list[str] = []
    answers = {CPU_QUERY: [sample(0.2, target="demo-1")]}
    handler = fake_prometheus(answers, calls)
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
        fleet = await read_fleet(PrometheusReader(http, "http://prom:9090"))
    assert sorted(calls) == sorted([CPU_QUERY, MEMORY_QUERY, DISK_QUERY, SERVICE_QUERY])
    assert fleet.cpu == [sample(0.2, target="demo-1")]
    assert fleet.scrape_targets is not None
    assert len(fleet.scrape_targets) == 2


@pytest.mark.parametrize("status", [None, 500, 200])
async def test_a_failing_prometheus_becomes_missing_readings(status: int | None) -> None:
    async with httpx.AsyncClient(transport=httpx.MockTransport(failing(status))) as http:
        fleet = await read_fleet(PrometheusReader(http, "http://prom:9090"))
    assert fleet == readings()
