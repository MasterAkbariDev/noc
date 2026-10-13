import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest

from noc.api import system
from noc.api.prometheus import PrometheusReader
from noc.api.schemas import ComponentHealth, ComponentStatus
from noc.api.system import (
    DatabaseSnapshot,
    alert_polling_component,
    database_component,
    describe_age,
    egress_component,
    prometheus_component,
    proxy_endpoints,
    updater_component,
    verdict,
    version_component,
    worker_component,
)
from noc.config import Settings
from noc.db.models import WorkerHeartbeat
from noc.llm.providers import ProviderConfig, ProvidersDocument
from noc.worker.heartbeat import PollStatus

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
INTERVAL = 15.0


def heartbeat(
    beat_age: float = 5,
    poll_ok_age: float | None = 3,
    poll_error: str | None = None,
    version: str = "test",
) -> WorkerHeartbeat:
    return WorkerHeartbeat(
        worker_id="host:1",
        started_at=NOW - timedelta(hours=2),
        last_beat_at=NOW - timedelta(seconds=beat_age),
        last_poll_ok_at=None if poll_ok_age is None else NOW - timedelta(seconds=poll_ok_age),
        last_poll_error=poll_error,
        last_poll_error_at=NOW - timedelta(seconds=10) if poll_error else None,
        version=version,
    )


def snapshot(beat: WorkerHeartbeat | None, migration: str | None = "0007") -> DatabaseSnapshot:
    return DatabaseSnapshot(heartbeat=beat, migration=migration, stuck=[])


def scrape_target(health: str, job: str = "node") -> dict[str, Any]:
    return {
        "labels": {"job": job, "instance": f"{job}:9100"},
        "health": health,
        "lastScrape": "2026-10-13T11:59:50.123456789Z",
        "lastError": "",
    }


def targets_body(*healths: str) -> dict[str, Any]:
    return {
        "status": "success",
        "data": {
            "activeTargets": [scrape_target(health) for health in healths],
            "droppedTargets": [],
        },
    }


async def prometheus_status(handler: httpx.MockTransport) -> ComponentHealth:
    async with httpx.AsyncClient(transport=handler) as http:
        return await prometheus_component(PrometheusReader(http, "http://prom:9090/"))


def serve(body: dict[str, Any], status: int = 200) -> httpx.MockTransport:
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body))


def providers_with_proxy(monkeypatch: pytest.MonkeyPatch) -> ProvidersDocument:
    monkeypatch.setenv("TEST_GEMINI_PROXY", "http://proxy.local:3128")
    return ProvidersDocument(
        providers={
            "gemini": ProviderConfig(
                base_url="https://example.invalid",
                api_key_env="TEST_GEMINI_KEY",
                proxy_env="TEST_GEMINI_PROXY",
                models={},
            ),
            "groq": ProviderConfig(
                base_url="https://example.invalid",
                api_key_env="TEST_GROQ_KEY",
                models={},
            ),
        },
        chains={},
    )


def components_with(**overrides: ComponentStatus) -> list[ComponentHealth]:
    keys = ["worker", "alert_polling", "prometheus", "egress", "database", "version", "updater"]
    return [system.component(key, overrides.get(key, "ok"), "summary") for key in keys]


def test_a_poll_status_remembers_the_last_success_and_failure() -> None:
    status = PollStatus()
    status.ok(NOW)
    status.failed(NOW + timedelta(seconds=10), "ConnectError")
    assert status.last_ok_at == NOW
    assert status.last_error == "ConnectError"
    assert status.last_error_at == NOW + timedelta(seconds=10)


def test_a_worker_that_never_reported_is_down() -> None:
    component = worker_component(snapshot(None), INTERVAL, NOW)
    assert component.status == "down"
    assert component.summary == "The worker has never reported"


@pytest.mark.parametrize(
    ("beat_age", "expected"),
    [(20, "ok"), (45, "ok"), (46, "degraded"), (300, "degraded"), (301, "down")],
)
def test_worker_status_follows_the_heartbeat_age(beat_age: float, expected: str) -> None:
    component = worker_component(snapshot(heartbeat(beat_age=beat_age)), INTERVAL, NOW)
    assert component.status == expected


def test_worker_summary_and_details_describe_the_last_beat() -> None:
    component = worker_component(snapshot(heartbeat(beat_age=12, version="0.9")), INTERVAL, NOW)
    assert component.summary == "Last heartbeat 12 s ago"
    assert component.details == {"version": "0.9"}
    assert component.since == NOW - timedelta(hours=2)


def test_without_a_database_answer_the_worker_is_unknown() -> None:
    assert worker_component(None, INTERVAL, NOW).status == "unknown"
    assert alert_polling_component(None, NOW).status == "unknown"


def test_a_fresh_poll_is_ok() -> None:
    component = alert_polling_component(snapshot(heartbeat(poll_ok_age=4)), NOW)
    assert component.status == "ok"
    assert component.summary == "Last alert poll succeeded 4 s ago"


def test_a_stale_poll_is_degraded_with_the_last_error() -> None:
    beat = heartbeat(poll_ok_age=90, poll_error="Prometheus did not answer the alert poll")
    component = alert_polling_component(snapshot(beat), NOW)
    assert component.status == "degraded"
    assert component.summary == (
        "Last alert poll succeeded 90 s ago; last error: Prometheus did not answer the alert poll"
    )
    assert component.details == {"last_error": "Prometheus did not answer the alert poll"}


def test_a_poll_that_never_succeeded_is_degraded() -> None:
    beat = heartbeat(poll_ok_age=None, poll_error="ConnectError")
    component = alert_polling_component(snapshot(beat), NOW)
    assert component.status == "degraded"
    assert component.summary == "No alert poll has succeeded yet; last error: ConnectError"


def test_alert_polling_is_unknown_without_any_heartbeat() -> None:
    component = alert_polling_component(snapshot(None), NOW)
    assert component.status == "unknown"
    assert component.summary == "No worker has reported, so polling is unknown"


async def test_all_scrape_targets_up_is_ok() -> None:
    component = await prometheus_status(serve(targets_body("up", "up")))
    assert component.status == "ok"
    assert component.details == {"up": "2/2"}


async def test_some_scrape_targets_down_is_degraded_with_a_count() -> None:
    component = await prometheus_status(serve(targets_body("up", "up", "up", "down")))
    assert component.status == "degraded"
    assert component.details == {"up": "3/4"}
    assert component.summary == "1 of 4 scrape targets are down"


async def test_prometheus_without_targets_is_unknown() -> None:
    component = await prometheus_status(serve(targets_body()))
    assert component.status == "unknown"


async def test_prometheus_that_answers_with_an_error_is_down() -> None:
    component = await prometheus_status(serve({"status": "error"}, status=200))
    assert component.status == "down"


async def test_prometheus_http_failure_is_down() -> None:
    component = await prometheus_status(serve({}, status=503))
    assert component.status == "down"


async def test_prometheus_connection_failure_is_down() -> None:
    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    component = await prometheus_status(httpx.MockTransport(refuse))
    assert component.status == "down"
    assert component.summary == "Prometheus cannot be reached"


async def test_never_scraped_targets_have_no_scrape_time() -> None:
    body = targets_body("down")
    body["data"]["activeTargets"][0]["lastScrape"] = "0001-01-01T00:00:00Z"
    async with httpx.AsyncClient(transport=serve(body)) as http:
        targets = await PrometheusReader(http, "http://prom:9090").targets()
    assert targets[0].last_scrape is None


async def test_vector_samples_carry_their_labels_and_value() -> None:
    body = {
        "status": "success",
        "data": {
            "resultType": "vector",
            "result": [{"metric": {"target": "demo-1"}, "value": [1.0, "0"]}],
        },
    }
    async with httpx.AsyncClient(transport=serve(body)) as http:
        samples = await PrometheusReader(http, "http://prom:9090").vector("up")
    assert [(sample.labels, sample.value) for sample in samples] == [({"target": "demo-1"}, 0.0)]


def test_the_proxy_endpoint_comes_from_the_provider_env(monkeypatch: pytest.MonkeyPatch) -> None:
    endpoints = proxy_endpoints(providers_with_proxy(monkeypatch))
    assert endpoints == {"gemini": ("proxy.local", 3128)}


async def refuse_to_probe(host: str, port: int) -> None:
    raise AssertionError("no proxy is configured, so nothing may be probed")


async def test_no_configured_proxy_means_unknown_egress() -> None:
    component = await egress_component({}, refuse_to_probe)
    assert component.status == "unknown"
    assert component.summary == "No egress proxy configured"


async def test_reachable_proxies_are_ok() -> None:
    async def connect(host: str, port: int) -> None:
        return None

    component = await egress_component({"gemini": ("proxy.local", 3128)}, connect)
    assert component.status == "ok"
    assert component.details == {"gemini": "reachable"}


async def test_an_unreachable_proxy_is_down() -> None:
    async def connect(host: str, port: int) -> None:
        raise ConnectionRefusedError(host)

    endpoints = {"gemini": ("proxy.local", 3128), "groq": ("proxy2.local", 3128)}
    component = await egress_component(endpoints, connect)
    assert component.status == "down"
    assert component.details == {"gemini": "unreachable", "groq": "unreachable"}


async def test_a_proxy_that_never_answers_times_out(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(system, "EGRESS_TIMEOUT_SECONDS", 0.01)

    async def connect(host: str, port: int) -> None:
        await asyncio.sleep(10)

    component = await egress_component({"gemini": ("proxy.local", 3128)}, connect)
    assert component.status == "down"


def test_database_down_when_the_snapshot_is_missing() -> None:
    assert database_component(None).status == "down"


def test_database_ok_reports_the_migration_or_unknown() -> None:
    assert database_component(snapshot(None, "0007")).details == {"migration": "0007"}
    component = database_component(snapshot(None, None))
    assert component.status == "ok"
    assert component.details == {"migration": "unknown"}


def test_version_component_reports_the_build() -> None:
    settings = Settings(version="main", git_sha="a1b2c3d4e5f60708", _env_file=None)
    component = version_component(settings)
    assert component.summary == "NOC main (a1b2c3d4e5f6)"
    assert component.details == {"version": "main", "git_sha": "a1b2c3d4e5f60708"}


def test_updater_without_a_status_file_is_unknown() -> None:
    assert updater_component(None).status == "unknown"


def test_updater_that_has_not_written_yet_is_unknown(tmp_path: Path) -> None:
    assert updater_component(tmp_path / "status.json").status == "unknown"


def test_updater_with_a_damaged_file_is_unknown(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_text("{not json", encoding="utf-8")
    assert updater_component(path).status == "unknown"


def write_update_status(path: Path, result: str) -> None:
    body = {
        "ts": "2026-10-13T11:55:00+00:00",
        "result": result,
        "image": "ghcr.io/example/noc:main",
        "message": f"update finished with {result}",
    }
    path.write_text(json.dumps(body), encoding="utf-8")


@pytest.mark.parametrize("result", ["unchanged", "deployed"])
def test_a_successful_update_result_is_ok(tmp_path: Path, result: str) -> None:
    path = tmp_path / "status.json"
    write_update_status(path, result)
    component = updater_component(path)
    assert component.status == "ok"
    assert component.details["result"] == result
    assert component.since == datetime(2026, 10, 13, 11, 55, tzinfo=UTC)


@pytest.mark.parametrize("result", ["failed", "rolled_back", "pull_failed"])
def test_a_failed_update_result_is_degraded(tmp_path: Path, result: str) -> None:
    path = tmp_path / "status.json"
    write_update_status(path, result)
    assert updater_component(path).status == "degraded"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({}, "ok"),
        ({"worker": "down"}, "down"),
        ({"database": "down"}, "down"),
        ({"prometheus": "degraded"}, "degraded"),
        ({"egress": "down"}, "degraded"),
        ({"updater": "unknown", "egress": "unknown"}, "ok"),
    ],
)
def test_the_verdict_combines_the_components(
    overrides: dict[str, ComponentStatus], expected: str
) -> None:
    assert verdict(components_with(**overrides)) == expected


@pytest.mark.parametrize(
    ("age", "expected"),
    [
        (timedelta(seconds=5), "5 s ago"),
        (timedelta(seconds=150), "2 min ago"),
        (timedelta(hours=2), "2 h ago"),
        (timedelta(seconds=-3), "0 s ago"),
    ],
)
def test_ages_are_described_in_plain_words(age: timedelta, expected: str) -> None:
    assert describe_age(age) == expected
