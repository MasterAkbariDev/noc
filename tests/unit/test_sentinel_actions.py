import json
import subprocess
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi.testclient import TestClient

from noc_sentinel.action_store import ActionStore
from noc_sentinel.actions import ACTION_TIMEOUT_SECONDS, ActionExecutor, ActionOutcome
from noc_sentinel.app import create_app
from noc_sentinel.config import ActionsConfig, SentinelConfig
from noc_sentinel.nonce_store import NonceStore
from noc_shared.actions import ActionRequest, ActionResult, ActionType, compute_action_hash
from noc_shared.resources import ManagedResource, ResourceKind
from noc_shared.signing import sign_request
from tests.support.builders import DEMO_SHOP, KEY_ID, SECRET, FakeSystemctl, sentinel_config

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
TARGET = "demo-1"
UNIT = "demo-shop.service"
INCIDENT = UUID("7d3c1f0e-2b8a-4c6d-9e51-0a1b2c3d4e5f")
RESTART_ARGV = ("/usr/bin/systemctl", "restart", UNIT)
START_ARGV = ("/usr/bin/systemctl", "start", UNIT)
ACTIONS_PATH = "/v1/actions/restart_service"
ACTION_LOOKUP_PATH = "/v1/actions/{action_id}"
WRONG_HASH = "0" * 64


class FakeActionRunner:
    def __init__(
        self,
        systemctl: FakeSystemctl,
        returncode: int = 0,
        after_state: str = "active",
        error: BaseException | None = None,
    ) -> None:
        self.systemctl = systemctl
        self.returncode = returncode
        self.after_state = after_state
        self.error = error
        self.calls: list[tuple[str, ...]] = []

    def run(self, argv: tuple[str, ...], timeout_seconds: int) -> int:
        self.calls.append(argv)
        if self.error is not None:
            raise self.error
        self.systemctl.active_state = self.after_state
        return self.returncode


def make_config(
    tmp_path: Path,
    max_per_hour: int = 3,
    enabled: bool = True,
    resources: list[ManagedResource] | None = None,
) -> SentinelConfig:
    base = sentinel_config(tmp_path)
    return base.model_copy(
        update={
            "actions": ActionsConfig(enabled=enabled, max_per_resource_per_hour=max_per_hour),
            "resources": resources if resources is not None else base.resources,
        }
    )


def make_request(
    action_type: ActionType = "restart_service",
    resource_id: str = DEMO_SHOP,
    attempt: int = 1,
    action_id: UUID | None = None,
    action_hash: str | None = None,
) -> ActionRequest:
    resolved_hash = action_hash or compute_action_hash(
        action_type, TARGET, resource_id, {}, INCIDENT, attempt
    )
    return ActionRequest(
        action_id=action_id or uuid4(),
        attempt_id=uuid4(),
        incident_id=INCIDENT,
        attempt=attempt,
        action_hash=resolved_hash,
        resource_id=resource_id,
        approval_id=uuid4(),
    )


def build_executor(
    store: ActionStore,
    config: SentinelConfig,
    systemctl: FakeSystemctl,
    runner: FakeActionRunner,
    sleeps: list[float] | None = None,
) -> ActionExecutor:
    sleep: Callable[[float], None] = sleeps.append if sleeps is not None else lambda _: None
    return ActionExecutor(config, systemctl, runner, store, lambda: NOW, sleep)


def running_executor(tmp_path: Path) -> tuple[ActionExecutor, FakeActionRunner, ActionStore]:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    store = ActionStore(tmp_path / "actions.db")
    return build_executor(store, config, systemctl, runner), runner, store


def assert_refused(outcome: ActionOutcome, status_code: int, code: str) -> None:
    assert outcome.status_code == status_code
    assert outcome.result.status == "refused"
    assert outcome.result.code == code


def test_success_records_before_after_and_exact_argv(tmp_path: Path) -> None:
    executor, runner, store = running_executor(tmp_path)
    request = make_request()
    outcome = executor.execute("restart_service", request)
    assert outcome.status_code == 200
    assert outcome.result.status == "succeeded"
    assert outcome.result.code is None
    assert outcome.result.deduplicated is False
    assert outcome.result.before is not None
    assert outcome.result.before.active_state == "failed"
    assert outcome.result.after is not None
    assert outcome.result.after.active_state == "active"
    assert runner.calls == [RESTART_ARGV]
    stored = store.get(request.action_id)
    assert stored is not None
    assert stored.result.status == "succeeded"


class UnreadableSystemctl(FakeSystemctl):
    def show(self, unit: str, properties: tuple[str, ...]) -> dict[str, str]:
        raise OSError("systemctl missing")


def test_unreadable_unit_state_fails_without_running_anything(tmp_path: Path) -> None:
    systemctl = UnreadableSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    store = ActionStore(tmp_path / "actions.db")
    executor = build_executor(store, make_config(tmp_path), systemctl, runner)
    request = make_request()
    outcome = executor.execute("restart_service", request)
    assert outcome.result.status == "failed"
    assert outcome.result.code == "STATUS_UNREADABLE"
    assert runner.calls == []
    stored = store.get(request.action_id)
    assert stored is not None
    assert stored.result.status == "failed"


def test_start_uses_the_start_verb(tmp_path: Path) -> None:
    executor, runner, _ = running_executor(tmp_path)
    executor.execute("start_service", make_request(action_type="start_service"))
    assert runner.calls == [START_ARGV]


def test_replay_returns_stored_result_without_running_again(tmp_path: Path) -> None:
    executor, runner, _ = running_executor(tmp_path)
    request = make_request()
    executor.execute("restart_service", request)
    replay = executor.execute("restart_service", request)
    assert replay.status_code == 200
    assert replay.result.status == "succeeded"
    assert replay.result.deduplicated is True
    assert runner.calls == [RESTART_ARGV]


def test_nonzero_exit_is_failed_with_exit_code(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl, returncode=1)
    sleeps: list[float] = []
    executor = build_executor(
        ActionStore(tmp_path / "actions.db"), config, systemctl, runner, sleeps
    )
    outcome = executor.execute("restart_service", make_request())
    assert outcome.result.status == "failed"
    assert outcome.result.code == "EXIT_1"
    assert sleeps == []


def test_timeout_is_failed_with_timeout_code(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    error = subprocess.TimeoutExpired(cmd=RESTART_ARGV, timeout=ACTION_TIMEOUT_SECONDS)
    runner = FakeActionRunner(systemctl, error=error)
    executor = build_executor(ActionStore(tmp_path / "actions.db"), config, systemctl, runner)
    outcome = executor.execute("restart_service", make_request())
    assert outcome.result.status == "failed"
    assert outcome.result.code == "TIMEOUT"
    assert outcome.result.after is not None
    assert outcome.result.after.active_state == "failed"


def test_unit_that_never_becomes_active_is_failed_not_active(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl, after_state="activating")
    sleeps: list[float] = []
    executor = build_executor(
        ActionStore(tmp_path / "actions.db"), config, systemctl, runner, sleeps
    )
    outcome = executor.execute("restart_service", make_request())
    assert outcome.result.status == "failed"
    assert outcome.result.code == "NOT_ACTIVE"
    assert sleeps == [1] * 10


def test_crash_left_executing_row_is_returned_and_not_rerun(tmp_path: Path) -> None:
    executor, runner, store = running_executor(tmp_path)
    request = make_request()
    store.insert_executing(
        request.action_hash,
        ActionResult(
            action_id=request.action_id,
            action_type="restart_service",
            resource_id=DEMO_SHOP,
            status="executing",
            code=None,
            message="action started",
            started_at=NOW,
            finished_at=None,
            before=None,
            after=None,
        ),
    )
    stored = executor.lookup(request.action_id)
    assert stored is not None
    assert stored.status == "executing"
    outcome = executor.execute("restart_service", request)
    assert outcome.status_code == 200
    assert outcome.result.status == "executing"
    assert outcome.result.deduplicated is True
    assert runner.calls == []


def test_halt_beats_every_later_check(tmp_path: Path) -> None:
    executor, runner, store = running_executor(tmp_path)
    (tmp_path / "HALT").write_text("")
    request = make_request(resource_id="svc:unknown", action_hash=WRONG_HASH)
    assert_refused(executor.execute("restart_service", request), 409, "HALTED")
    assert store.get(request.action_id) is None
    assert runner.calls == []


def test_hash_mismatch_is_422_and_not_stored(tmp_path: Path) -> None:
    executor, runner, store = running_executor(tmp_path)
    request = make_request(action_hash=WRONG_HASH)
    assert_refused(executor.execute("restart_service", request), 422, "HASH_MISMATCH")
    assert store.get(request.action_id) is None
    assert runner.calls == []


def test_reused_action_id_with_other_hash_is_409(tmp_path: Path) -> None:
    executor, runner, _ = running_executor(tmp_path)
    first = make_request()
    executor.execute("restart_service", first)
    other = make_request(attempt=2, action_id=first.action_id)
    assert_refused(executor.execute("restart_service", other), 409, "ACTION_ID_REUSED")
    assert runner.calls == [RESTART_ARGV]


def test_replay_beats_allow_list_after_config_change(tmp_path: Path) -> None:
    executor, _, store = running_executor(tmp_path)
    request = make_request()
    executor.execute("restart_service", request)
    revoked = make_config(
        tmp_path,
        resources=[
            ManagedResource(
                id=DEMO_SHOP,
                kind=ResourceKind.SYSTEMD_UNIT,
                name=UNIT,
                allowed_actions=(),
            )
        ],
    )
    later_runner = FakeActionRunner(FakeSystemctl(active_state="failed"))
    later = build_executor(store, revoked, FakeSystemctl(), later_runner)
    replay = later.execute("restart_service", request)
    assert replay.status_code == 200
    assert replay.result.deduplicated is True
    assert later_runner.calls == []


@pytest.mark.parametrize("resource_id", ["svc:missing", "ctr:demo-db"])
def test_unregistered_or_non_unit_resource_is_403_not_allowed(
    tmp_path: Path, resource_id: str
) -> None:
    executor, runner, _ = running_executor(tmp_path)
    request = make_request(resource_id=resource_id)
    assert_refused(executor.execute("restart_service", request), 403, "NOT_ALLOWED")
    assert runner.calls == []


def test_action_missing_from_allowed_actions_is_403(tmp_path: Path) -> None:
    config = make_config(
        tmp_path,
        resources=[
            ManagedResource(
                id=DEMO_SHOP,
                kind=ResourceKind.SYSTEMD_UNIT,
                name=UNIT,
                allowed_actions=("start_service",),
            )
        ],
    )
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    executor = build_executor(ActionStore(tmp_path / "actions.db"), config, systemctl, runner)
    assert_refused(executor.execute("restart_service", make_request()), 403, "NOT_ALLOWED")
    assert runner.calls == []


@pytest.mark.parametrize("unit", ["sshd.service", "docker.service", "systemd-resolved.service"])
def test_protected_units_are_403_even_when_allowed(tmp_path: Path, unit: str) -> None:
    resource_id = "svc:" + unit.split(".")[0]
    config = make_config(
        tmp_path,
        resources=[
            ManagedResource(
                id=resource_id,
                kind=ResourceKind.SYSTEMD_UNIT,
                name=unit,
                allowed_actions=("restart_service",),
            )
        ],
    )
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    executor = build_executor(ActionStore(tmp_path / "actions.db"), config, systemctl, runner)
    request = make_request(resource_id=resource_id)
    assert_refused(executor.execute("restart_service", request), 403, "PROTECTED")
    assert runner.calls == []


def test_rate_limit_refuses_the_execution_that_would_exceed_the_hour(tmp_path: Path) -> None:
    executor, runner, store = running_executor(tmp_path)
    for _ in range(3):
        assert executor.execute("restart_service", make_request()).result.status == "succeeded"
    refused = make_request()
    assert_refused(executor.execute("restart_service", refused), 429, "RATE_LIMITED")
    assert store.get(refused.action_id) is None
    assert store.count_since(DEMO_SHOP, NOW - timedelta(hours=1)) == 3
    assert len(runner.calls) == 3


def test_rate_window_forgets_executions_older_than_an_hour(tmp_path: Path) -> None:
    _, _, store = running_executor(tmp_path)
    store.insert_executing(
        "b" * 64,
        ActionResult(
            action_id=uuid4(),
            action_type="restart_service",
            resource_id=DEMO_SHOP,
            status="succeeded",
            code=None,
            message="old",
            started_at=NOW - timedelta(hours=2),
            finished_at=None,
            before=None,
            after=None,
        ),
    )
    assert store.count_since(DEMO_SHOP, NOW - timedelta(hours=1)) == 0


def signed_post(client: TestClient, path: str, payload: dict[str, Any]) -> httpx.Response:
    body = json.dumps(payload).encode()
    headers = sign_request(KEY_ID, SECRET, "POST", path, body, now=NOW).as_dict()
    return client.post(path, content=body, headers={**headers, "Content-Type": "application/json"})


def signed_get(client: TestClient, path: str) -> httpx.Response:
    headers = sign_request(KEY_ID, SECRET, "GET", path, b"", now=NOW).as_dict()
    return client.get(path, headers=headers)


def router_client(
    tmp_path: Path, config: SentinelConfig, runner: FakeActionRunner, systemctl: FakeSystemctl
) -> TestClient:
    app = create_app(
        config,
        systemctl,
        NonceStore(tmp_path / "nonces.sqlite3", ttl_seconds=300),
        config.load_secrets(),
        clock=lambda: NOW,
        action_runner=runner,
    )
    return TestClient(app)


def test_router_is_not_mounted_when_actions_are_disabled(tmp_path: Path) -> None:
    config = make_config(tmp_path, enabled=False)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    app = create_app(
        config,
        systemctl,
        NonceStore(tmp_path / "nonces.sqlite3", ttl_seconds=300),
        config.load_secrets(),
        clock=lambda: NOW,
        action_runner=runner,
    )
    paths = {str(getattr(route, "path", "")) for route in app.routes}
    assert "/v1/actions/{action_type}" not in paths
    assert "/v1/actions/{action_id}" not in paths
    assert runner.calls == []


def test_unsigned_action_is_rejected(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    client = router_client(tmp_path, config, runner, systemctl)
    payload = make_request().model_dump(mode="json")
    response = client.post(ACTIONS_PATH, json=payload)
    assert response.status_code == 401
    assert runner.calls == []


def test_unknown_action_type_is_404(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    client = router_client(tmp_path, config, runner, systemctl)
    payload = make_request().model_dump(mode="json")
    assert signed_post(client, "/v1/actions/run_command", payload).status_code == 404
    assert runner.calls == []


def test_signed_restart_returns_200_with_before_and_after(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    client = router_client(tmp_path, config, runner, systemctl)
    request = make_request()
    response = signed_post(client, ACTIONS_PATH, request.model_dump(mode="json"))
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["before"]["active_state"] == "failed"
    assert body["after"]["active_state"] == "active"
    assert runner.calls == [RESTART_ARGV]
    stored = signed_get(client, f"/v1/actions/{request.action_id}")
    assert stored.status_code == 200
    assert stored.json()["status"] == "succeeded"


def test_halt_refusal_is_409_and_not_stored(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    runner = FakeActionRunner(systemctl)
    client = router_client(tmp_path, config, runner, systemctl)
    (tmp_path / "HALT").write_text("")
    request = make_request()
    payload = request.model_dump(mode="json")
    response = signed_post(client, ACTIONS_PATH, payload)
    assert response.status_code == 409
    assert response.json()["code"] == "HALTED"
    assert response.json()["status"] == "refused"
    assert signed_get(client, f"/v1/actions/{request.action_id}").status_code == 404
    assert runner.calls == []


def test_unknown_action_lookup_is_404(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    systemctl = FakeSystemctl(active_state="failed")
    client = router_client(tmp_path, config, FakeActionRunner(systemctl), systemctl)
    assert signed_get(client, ACTION_LOOKUP_PATH.format(action_id=uuid4())).status_code == 404
