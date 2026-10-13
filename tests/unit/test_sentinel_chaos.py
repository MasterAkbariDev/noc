import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

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


def chaos_config(tmp_path: Path, environment: str = "lab", enabled: bool = True) -> SentinelConfig:
    base = sentinel_config(tmp_path, environment)
    key_file = tmp_path / f"{CHAOS_KEY_ID}.key"
    key_file.write_bytes(CHAOS_SECRET)
    chaos = ChaosConfig(enabled=enabled, key_id=CHAOS_KEY_ID, key_file=key_file)
    return base.model_copy(update={"chaos": chaos})


def build(
    tmp_path: Path,
    environment: str = "lab",
    enabled: bool = True,
    runner: FakeChaosRunner | None = None,
) -> Harness:
    config = chaos_config(tmp_path, environment, enabled)
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
