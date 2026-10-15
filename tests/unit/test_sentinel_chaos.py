import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

import noc_sentinel.chaos as chaos_module
from noc_sentinel.app import create_app
from noc_sentinel.config import ChaosConfig, SentinelConfig
from noc_sentinel.nonce_store import NonceStore
from noc_shared.resources import ManagedResource, ResourceKind
from noc_shared.signing import sign_request
from tests.support.builders import DEMO_SHOP, KEY_ID, SECRET, FakeSystemctl, sentinel_config

CHAOS_KEY_ID = "noc-chaos-test-key"
CHAOS_SECRET = b"fedcba9876543210fedcba9876543210"
NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
START = "/v1/chaos/service-down/start"
STOP = "/v1/chaos/service-down/stop"
STATUS = "/v1/chaos/status"
UNIT = "demo-shop.service"
RESTORE_TIMER = "noc-chaos-restore-demo-shop-service.timer"
START_PAYLOAD = {"resource_id": DEMO_SHOP, "ttl_seconds": 300}
CPU_START = "/v1/chaos/cpu-burn/start"
CPU_STOP = "/v1/chaos/cpu-burn/stop"
CPU_UNIT = "noc-chaos-cpu-burn"
CPU_RESTORE_TIMER = "noc-chaos-restore-cpu-burn.timer"
DISK_START = "/v1/chaos/disk-fill/start"
DISK_STOP = "/v1/chaos/disk-fill/stop"
APP_START = "/v1/chaos/app-fault/start"
APP_STOP = "/v1/chaos/app-fault/stop"
APP_PORT = 8099
APP_RESTORE_UNIT = "noc-chaos-restore-app-svc-demo-shop"
APP_RESET = (
    "/usr/bin/curl",
    "-fsS",
    "--max-time",
    "5",
    "-X",
    "POST",
    f"http://127.0.0.1:{APP_PORT}/chaos/reset",
)


class MutableClock:
    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now


class FakeChaosRunner:
    def __init__(self, failing: frozenset[tuple[str, ...]] = frozenset()) -> None:
        self.failing = failing
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...]) -> int:
        self.calls.append(argv)
        return 1 if argv in self.failing else 0


@dataclass
class Harness:
    client: TestClient
    runner: FakeChaosRunner
    clock: MutableClock
    config: SentinelConfig


def chaos_config(
    tmp_path: Path,
    environment: str = "lab",
    enabled: bool = True,
    disk_fill_dir: Path | None = None,
    app_chaos_ports: dict[str, int] | None = None,
) -> SentinelConfig:
    base = sentinel_config(tmp_path, environment)
    key_file = tmp_path / f"{CHAOS_KEY_ID}.key"
    key_file.write_bytes(CHAOS_SECRET)
    chaos = ChaosConfig(
        enabled=enabled,
        key_id=CHAOS_KEY_ID,
        key_file=key_file,
        disk_fill_dir=disk_fill_dir,
        app_chaos_ports=app_chaos_ports or {},
    )
    return base.model_copy(update={"chaos": chaos})


def build(
    tmp_path: Path,
    environment: str = "lab",
    enabled: bool = True,
    runner: FakeChaosRunner | None = None,
    disk_fill_dir: Path | None = None,
    app_chaos_ports: dict[str, int] | None = None,
) -> Harness:
    config = chaos_config(tmp_path, environment, enabled, disk_fill_dir, app_chaos_ports)
    clock = MutableClock(NOW)
    chaos_runner = runner if runner is not None else FakeChaosRunner()
    store = NonceStore(tmp_path / "nonces.sqlite3", ttl_seconds=300)
    app = create_app(
        config,
        FakeSystemctl(),
        store,
        config.load_secrets(),
        clock=clock,
        chaos_runner=chaos_runner,
    )
    return Harness(TestClient(app), chaos_runner, clock, config)


def send(
    harness: Harness,
    method: str,
    path: str,
    payload: dict[str, object] | None = None,
    key_id: str = CHAOS_KEY_ID,
    secret: bytes = CHAOS_SECRET,
) -> httpx.Response:
    body = json.dumps(payload).encode() if payload is not None else b""
    headers = sign_request(key_id, secret, method, path, body, now=harness.clock()).as_dict()
    return harness.client.request(
        method, path, content=body, headers={**headers, "Content-Type": "application/json"}
    )


def test_disabled_chaos_is_not_mounted(tmp_path: Path) -> None:
    harness = build(tmp_path, enabled=False)
    assert send(harness, "GET", STATUS).status_code == 404
    assert send(harness, "POST", START, START_PAYLOAD).status_code == 404
    assert harness.runner.calls == []


def test_prod_environment_never_mounts_chaos_even_when_enabled(tmp_path: Path) -> None:
    harness = build(tmp_path, environment="prod", enabled=True)
    assert send(harness, "GET", STATUS).status_code == 404
    assert send(harness, "POST", START, START_PAYLOAD).status_code == 404
    assert harness.runner.calls == []


def test_unsigned_chaos_request_is_rejected(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = harness.client.post(START, json=START_PAYLOAD)
    assert response.status_code == 401
    assert harness.runner.calls == []


def test_tool_key_is_rejected_on_chaos_routes(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", START, START_PAYLOAD, key_id=KEY_ID, secret=SECRET)
    assert response.status_code == 401
    assert harness.runner.calls == []


def test_chaos_key_is_rejected_on_tool_and_inventory_routes(tmp_path: Path) -> None:
    harness = build(tmp_path)
    tool = send(
        harness,
        "POST",
        "/v1/tools/get_service_status",
        {"args": {"resource_id": DEMO_SHOP}},
    )
    inventory = send(harness, "GET", "/v1/inventory")
    assert tool.status_code == 401
    assert tool.json()["detail"] == "unknown_key"
    assert inventory.status_code == 401


def test_ttl_above_the_maximum_is_rejected(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", START, {"resource_id": DEMO_SHOP, "ttl_seconds": 901})
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_unregistered_resource_is_not_found(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", START, {"resource_id": "svc:unknown", "ttl_seconds": 60})
    assert response.status_code == 404
    assert response.json()["detail"] == "NOT_FOUND"
    assert harness.runner.calls == []


def test_registered_resource_of_another_kind_is_refused(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", START, {"resource_id": "ctr:demo-db", "ttl_seconds": 60})
    assert response.status_code == 403
    assert harness.runner.calls == []


def test_unit_without_chaos_opt_in_is_refused(tmp_path: Path) -> None:
    harness = build(tmp_path)
    read_only = ManagedResource(
        id="svc:ssh", kind=ResourceKind.SYSTEMD_UNIT, name="ssh.service", allowed_actions=()
    )
    harness.config.resources.append(read_only)
    response = send(harness, "POST", START, {"resource_id": "svc:ssh", "ttl_seconds": 60})
    assert response.status_code == 403
    assert harness.runner.calls == []


def test_halt_file_refuses_chaos_start(tmp_path: Path) -> None:
    harness = build(tmp_path)
    harness.config.halt_file.write_text("")
    response = send(harness, "POST", START, START_PAYLOAD)
    assert response.status_code == 409
    assert response.json()["detail"] == "HALTED"
    assert harness.runner.calls == []


def test_start_runs_exactly_the_fixed_argv_lists(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", START, START_PAYLOAD)
    assert response.status_code == 200
    assert response.json()["active"] is True
    assert harness.runner.calls == [
        (
            "/usr/bin/systemd-run",
            "--unit=noc-chaos-restore-demo-shop-service",
            "--on-active=300",
            "/usr/bin/systemctl",
            "start",
            UNIT,
        ),
        ("/usr/bin/systemctl", "stop", UNIT),
    ]


def test_second_start_while_active_is_refused(tmp_path: Path) -> None:
    harness = build(tmp_path)
    assert send(harness, "POST", START, START_PAYLOAD).status_code == 200
    response = send(harness, "POST", START, START_PAYLOAD)
    assert response.status_code == 409
    assert response.json()["detail"] == "ALREADY_ACTIVE"
    assert len(harness.runner.calls) == 2


def test_status_shows_the_active_chaos(tmp_path: Path) -> None:
    harness = build(tmp_path)
    send(harness, "POST", START, START_PAYLOAD)
    status = send(harness, "GET", STATUS).json()
    assert status["active"] is True
    assert status["resource_id"] == DEMO_SHOP
    assert status["unit"] == UNIT


def test_stop_starts_the_unit_and_removes_the_timer(tmp_path: Path) -> None:
    harness = build(tmp_path)
    send(harness, "POST", START, START_PAYLOAD)
    response = send(harness, "POST", STOP, {"resource_id": DEMO_SHOP})
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert harness.runner.calls[2:] == [
        ("/usr/bin/systemctl", "start", UNIT),
        ("/usr/bin/systemctl", "stop", RESTORE_TIMER),
    ]
    assert send(harness, "GET", STATUS).json()["active"] is False


def test_stop_without_active_chaos_is_refused(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", STOP, {"resource_id": DEMO_SHOP})
    assert response.status_code == 409
    assert harness.runner.calls == []


def test_expired_chaos_is_no_longer_active(tmp_path: Path) -> None:
    harness = build(tmp_path)
    send(harness, "POST", START, {"resource_id": DEMO_SHOP, "ttl_seconds": 60})
    harness.clock.now = NOW + timedelta(seconds=61)
    assert send(harness, "GET", STATUS).json()["active"] is False
    assert (
        send(harness, "POST", START, {"resource_id": DEMO_SHOP, "ttl_seconds": 60}).status_code
        == 200
    )


def test_failed_stop_leaves_no_active_chaos_and_cleans_the_timer(tmp_path: Path) -> None:
    failing = frozenset({("/usr/bin/systemctl", "stop", UNIT)})
    harness = build(tmp_path, runner=FakeChaosRunner(failing=failing))
    response = send(harness, "POST", START, START_PAYLOAD)
    assert response.status_code == 500
    assert send(harness, "GET", STATUS).json()["active"] is False
    assert harness.runner.calls[-1] == ("/usr/bin/systemctl", "stop", RESTORE_TIMER)


def test_metric_reports_whether_chaos_is_mounted(tmp_path: Path) -> None:
    (tmp_path / "on").mkdir()
    (tmp_path / "off").mkdir()
    mounted = build(tmp_path / "on", enabled=True)
    unmounted = build(tmp_path / "off", enabled=False)
    assert "noc_sentinel_chaos_enabled 1.0" in mounted.client.get("/metrics").text
    assert "noc_sentinel_chaos_enabled 0.0" in unmounted.client.get("/metrics").text


def test_enabled_chaos_without_a_key_fails_validation() -> None:
    with pytest.raises(ValidationError):
        SentinelConfig.model_validate(
            {"target": "demo-1", "environment": "lab", "key_files": {}, "chaos": {"enabled": True}}
        )


def test_chaos_key_cannot_also_be_a_tool_key(tmp_path: Path) -> None:
    key_file = tmp_path / "shared.key"
    with pytest.raises(ValidationError):
        SentinelConfig.model_validate(
            {
                "target": "demo-1",
                "environment": "lab",
                "key_files": {CHAOS_KEY_ID: str(key_file)},
                "chaos": {
                    "enabled": True,
                    "key_id": CHAOS_KEY_ID,
                    "key_file": str(key_file),
                },
            }
        )


def test_chaos_ttl_ceiling_cannot_be_raised_in_config() -> None:
    with pytest.raises(ValidationError):
        ChaosConfig(max_ttl_seconds=901)


def test_disk_fill_directory_must_be_absolute() -> None:
    with pytest.raises(ValidationError):
        ChaosConfig(disk_fill_dir=Path("relative/dir"))


def fake_disk(monkeypatch: pytest.MonkeyPatch, total: int, used: int) -> None:
    usage = SimpleNamespace(total=total, used=used, free=total - used)
    monkeypatch.setattr(chaos_module.shutil, "disk_usage", lambda _path: usage)


def fill_harness(tmp_path: Path) -> Harness:
    fill_dir = tmp_path / "fill"
    fill_dir.mkdir()
    return build(tmp_path, disk_fill_dir=fill_dir)


def test_cpu_burn_start_runs_the_fixed_argv_with_a_restore_timer(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", CPU_START, {"workers": 2, "ttl_seconds": 120})
    assert response.status_code == 200
    assert response.json()["scenario"] == "cpu-burn"
    assert response.json()["unit"] == CPU_UNIT
    assert harness.runner.calls == [
        (
            "/usr/bin/systemd-run",
            "--unit=noc-chaos-restore-cpu-burn",
            "--on-active=120",
            "/usr/bin/systemctl",
            "stop",
            CPU_UNIT,
        ),
        (
            "/usr/bin/systemd-run",
            "--unit=noc-chaos-cpu-burn",
            "--property=RuntimeMaxSec=120",
            "--property=Nice=0",
            "/bin/bash",
            "-c",
            "for i in $(seq 2); do (exec -a report-gen /usr/bin/yes > /dev/null) & done; wait",
        ),
    ]


@pytest.mark.parametrize("workers", [0, 9])
def test_cpu_burn_workers_outside_the_range_are_rejected(tmp_path: Path, workers: int) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", CPU_START, {"workers": workers, "ttl_seconds": 60})
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_cpu_burn_rejects_a_non_integer_worker_count(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", CPU_START, {"workers": "2; rm -rf /", "ttl_seconds": 60})
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_cpu_burn_ttl_above_the_maximum_is_rejected(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", CPU_START, {"workers": 1, "ttl_seconds": 901})
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_cpu_burn_extra_field_is_rejected(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", CPU_START, {"workers": 1, "ttl_seconds": 60, "command": "id"})
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_cpu_burn_stop_stops_the_unit_and_removes_the_timer(tmp_path: Path) -> None:
    harness = build(tmp_path)
    send(harness, "POST", CPU_START, {"workers": 1, "ttl_seconds": 60})
    response = send(harness, "POST", CPU_STOP, {})
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert harness.runner.calls[2:] == [
        ("/usr/bin/systemctl", "stop", CPU_UNIT),
        ("/usr/bin/systemctl", "stop", CPU_RESTORE_TIMER),
    ]


def test_cpu_burn_stop_without_active_cpu_burn_is_refused(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", CPU_STOP, {})
    assert response.status_code == 409
    assert harness.runner.calls == []


def test_one_slot_is_shared_across_all_scenarios(tmp_path: Path) -> None:
    harness = build(tmp_path)
    assert send(harness, "POST", START, START_PAYLOAD).status_code == 200
    assert send(harness, "POST", CPU_START, {"workers": 1, "ttl_seconds": 60}).status_code == 409
    assert send(harness, "POST", CPU_STOP, {}).status_code == 409
    assert send(harness, "POST", STOP, {"resource_id": DEMO_SHOP}).status_code == 200
    assert send(harness, "POST", CPU_START, {"workers": 1, "ttl_seconds": 60}).status_code == 200


def test_halt_file_refuses_cpu_burn_and_disk_fill(tmp_path: Path) -> None:
    harness = fill_harness(tmp_path)
    harness.config.halt_file.write_text("")
    cpu = send(harness, "POST", CPU_START, {"workers": 1, "ttl_seconds": 60})
    disk = send(harness, "POST", DISK_START, {"target_percent": 80, "ttl_seconds": 60})
    assert cpu.json()["detail"] == "HALTED"
    assert disk.json()["detail"] == "HALTED"
    assert harness.runner.calls == []


def test_disk_fill_without_a_configured_directory_is_not_configured(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", DISK_START, {"target_percent": 80, "ttl_seconds": 60})
    assert response.status_code == 409
    assert response.json()["detail"] == "NOT_CONFIGURED"
    assert harness.runner.calls == []


def test_disk_fill_start_allocates_up_to_the_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = fill_harness(tmp_path)
    fake_disk(monkeypatch, total=10_000_000_000, used=2_000_000_000)
    response = send(harness, "POST", DISK_START, {"target_percent": 60, "ttl_seconds": 300})
    fill_path = str(harness.config.chaos.disk_fill_dir) + "/noc-chaos-fill.log"
    assert response.status_code == 200
    assert response.json()["scenario"] == "disk-fill"
    assert harness.runner.calls == [
        (
            "/usr/bin/systemd-run",
            "--unit=noc-chaos-restore-disk-fill",
            "--on-active=300",
            "/usr/bin/rm",
            "-f",
            fill_path,
        ),
        ("/usr/bin/fallocate", "-l", "4000000000", fill_path),
    ]


def test_disk_fill_respects_the_minimum_free_space(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = fill_harness(tmp_path)
    fake_disk(monkeypatch, total=10_000_000_000, used=2_000_000_000)
    harness.config.chaos.disk_fill_min_free_bytes = 9_500_000_000
    response = send(harness, "POST", DISK_START, {"target_percent": 95, "ttl_seconds": 60})
    assert response.status_code == 409
    assert response.json()["detail"] == "NOT_POSSIBLE"
    assert harness.runner.calls == []


def test_disk_fill_is_not_possible_when_already_above_target(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = fill_harness(tmp_path)
    fake_disk(monkeypatch, total=10_000_000_000, used=8_000_000_000)
    response = send(harness, "POST", DISK_START, {"target_percent": 60, "ttl_seconds": 60})
    assert response.json()["detail"] == "NOT_POSSIBLE"
    assert harness.runner.calls == []


def test_disk_fill_stop_removes_the_file_and_the_timer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    harness = fill_harness(tmp_path)
    fake_disk(monkeypatch, total=10_000_000_000, used=2_000_000_000)
    send(harness, "POST", DISK_START, {"target_percent": 60, "ttl_seconds": 300})
    response = send(harness, "POST", DISK_STOP, {})
    fill_path = str(harness.config.chaos.disk_fill_dir) + "/noc-chaos-fill.log"
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert harness.runner.calls[2:] == [
        ("/usr/bin/rm", "-f", fill_path),
        ("/usr/bin/systemctl", "stop", "noc-chaos-restore-disk-fill.timer"),
    ]


def test_disk_fill_failed_allocation_is_rolled_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fill_dir = tmp_path / "fill"
    fill_dir.mkdir()
    fill_path = str(fill_dir) + "/noc-chaos-fill.log"
    failing = frozenset({("/usr/bin/fallocate", "-l", "4000000000", fill_path)})
    harness = build(tmp_path, runner=FakeChaosRunner(failing=failing), disk_fill_dir=fill_dir)
    fake_disk(monkeypatch, total=10_000_000_000, used=2_000_000_000)
    response = send(harness, "POST", DISK_START, {"target_percent": 60, "ttl_seconds": 300})
    assert response.status_code == 500
    assert send(harness, "GET", STATUS).json()["active"] is False
    assert harness.runner.calls[-2:] == [
        ("/usr/bin/rm", "-f", fill_path),
        ("/usr/bin/systemctl", "stop", "noc-chaos-restore-disk-fill.timer"),
    ]


@pytest.mark.parametrize("target", [49, 96])
def test_disk_fill_target_outside_the_range_is_rejected(tmp_path: Path, target: int) -> None:
    harness = fill_harness(tmp_path)
    response = send(harness, "POST", DISK_START, {"target_percent": target, "ttl_seconds": 60})
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_disk_fill_ttl_above_the_maximum_is_rejected(tmp_path: Path) -> None:
    harness = fill_harness(tmp_path)
    response = send(harness, "POST", DISK_START, {"target_percent": 60, "ttl_seconds": 901})
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_disk_fill_extra_field_is_rejected(tmp_path: Path) -> None:
    harness = fill_harness(tmp_path)
    response = send(
        harness,
        "POST",
        DISK_START,
        {"target_percent": 60, "ttl_seconds": 60, "path": "/etc/passwd"},
    )
    assert response.status_code == 422
    assert harness.runner.calls == []


def test_status_reports_the_scenario_of_the_active_injection(tmp_path: Path) -> None:
    harness = build(tmp_path)
    assert send(harness, "GET", STATUS).json()["scenario"] is None
    send(harness, "POST", CPU_START, {"workers": 1, "ttl_seconds": 60})
    assert send(harness, "GET", STATUS).json()["scenario"] == "cpu-burn"


def test_disk_fill_size_respects_space_reserved_for_root() -> None:
    gib = 1024**3
    total, used, reserved = 20 * gib, 9 * gib, gib
    available = total - used - reserved
    size = chaos_module.fill_bytes(total, used, available, 95, gib)
    assert size == available - gib
    assert chaos_module.fill_bytes(total, used, available, 50, gib) == gib


def app_harness(tmp_path: Path, runner: FakeChaosRunner | None = None) -> Harness:
    return build(tmp_path, runner=runner, app_chaos_ports={DEMO_SHOP: APP_PORT})


def app_start(fault: str, ttl_seconds: int = 300) -> dict[str, object]:
    return {"resource_id": DEMO_SHOP, "fault": fault, "ttl_seconds": ttl_seconds}


def set_fault_argv(body: str) -> tuple[str, ...]:
    return (
        "/usr/bin/curl",
        "-fsS",
        "--max-time",
        "5",
        "-X",
        "PUT",
        "-H",
        "Content-Type: application/json",
        "--data",
        body,
        f"http://127.0.0.1:{APP_PORT}/chaos",
    )


def test_app_fault_start_runs_the_fixed_curl_argv_with_a_restore_timer(tmp_path: Path) -> None:
    harness = app_harness(tmp_path)
    response = send(harness, "POST", APP_START, app_start("memory_leak", 600))
    assert response.status_code == 200
    assert response.json()["scenario"] == "app-fault"
    assert response.json()["fault"] == "memory_leak"
    assert harness.runner.calls == [
        (
            "/usr/bin/systemd-run",
            f"--unit={APP_RESTORE_UNIT}",
            "--on-active=600",
            *APP_RESET,
        ),
        set_fault_argv('{"memory_leak": true}'),
    ]


def test_upstream_delay_uses_the_configured_delay(tmp_path: Path) -> None:
    harness = app_harness(tmp_path)
    send(harness, "POST", APP_START, app_start("upstream_delay"))
    assert harness.runner.calls[1] == set_fault_argv('{"upstream_delay_ms": 2500}')


def test_app_fault_on_a_resource_without_a_chaos_port_is_refused(tmp_path: Path) -> None:
    harness = build(tmp_path)
    response = send(harness, "POST", APP_START, app_start("memory_leak"))
    assert response.status_code == 403
    assert harness.runner.calls == []


def test_app_fault_on_an_unregistered_resource_is_not_found(tmp_path: Path) -> None:
    harness = app_harness(tmp_path)
    payload = {"resource_id": "svc:unknown", "fault": "memory_leak", "ttl_seconds": 60}
    response = send(harness, "POST", APP_START, payload)
    assert response.status_code == 404
    assert harness.runner.calls == []


@pytest.mark.parametrize(
    "payload",
    [
        {"resource_id": DEMO_SHOP, "fault": "rm -rf /", "ttl_seconds": 60},
        {"resource_id": DEMO_SHOP, "fault": "memory_leak", "ttl_seconds": 901},
        {"resource_id": DEMO_SHOP, "fault": "memory_leak", "ttl_seconds": 60, "url": "x"},
    ],
)
def test_app_fault_rejects_unknown_faults_long_ttls_and_extra_fields(
    tmp_path: Path, payload: dict[str, object]
) -> None:
    harness = app_harness(tmp_path)
    assert send(harness, "POST", APP_START, payload).status_code == 422
    assert harness.runner.calls == []


def test_app_fault_stop_resets_the_app_and_removes_the_timer(tmp_path: Path) -> None:
    harness = app_harness(tmp_path)
    send(harness, "POST", APP_START, app_start("connection_leak"))
    response = send(harness, "POST", APP_STOP, {"resource_id": DEMO_SHOP})
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert harness.runner.calls[2:] == [
        APP_RESET,
        ("/usr/bin/systemctl", "stop", f"{APP_RESTORE_UNIT}.timer"),
    ]


def test_failed_app_fault_start_is_rolled_back(tmp_path: Path) -> None:
    failing = frozenset({set_fault_argv('{"memory_leak": true}')})
    harness = app_harness(tmp_path, FakeChaosRunner(failing))
    response = send(harness, "POST", APP_START, app_start("memory_leak"))
    assert response.status_code == 500
    assert harness.runner.calls[2:] == [
        APP_RESET,
        ("/usr/bin/systemctl", "stop", f"{APP_RESTORE_UNIT}.timer"),
    ]
    assert send(harness, "GET", STATUS).json()["active"] is False


def test_app_chaos_ports_must_be_unprivileged() -> None:
    with pytest.raises(ValidationError):
        ChaosConfig(app_chaos_ports={DEMO_SHOP: 80})
