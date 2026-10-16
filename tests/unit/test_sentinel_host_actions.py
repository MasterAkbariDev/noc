from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from noc_sentinel.action_store import ActionStore
from noc_sentinel.actions import ActionExecutor
from noc_sentinel.config import ActionsConfig, SentinelConfig
from noc_sentinel.host_actions import HOST_ACTIONS, host_action_unit
from noc_sentinel.tools.host import unit_from_cgroup
from noc_shared.actions import ActionRequest, ActionType, HostActionType, compute_action_hash
from noc_shared.resources import ManagedResource, ResourceKind
from tests.support.builders import FakeSystemctl, sentinel_config

NOW = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
INCIDENT = UUID("2f0c9a3e-6d1b-4e2a-9c8f-1a2b3c4d5e6f")
SYSTEMCTL = "/usr/bin/systemctl"
REPORT_JOB = ManagedResource(
    id="job:report-gen",
    kind=ResourceKind.BATCH_UNIT,
    name="noc-chaos-cpu-burn.service",
    allowed_actions=("throttle_cpu", "stop_service", "limit_memory"),
)
DEMO_DATA = ManagedResource(
    id="dir:demo-data",
    kind=ResourceKind.DIRECTORY,
    name="/srv/demo-data",
    allowed_actions=("rotate_logs", "clean_temp_dir"),
)
JOURNAL = ManagedResource(
    id="log:journal",
    kind=ResourceKind.LOG_SOURCE,
    name="/var/log/journal",
    allowed_actions=("vacuum_journal",),
)
DOCKER = ManagedResource(
    id="docker:engine",
    kind=ResourceKind.DOCKER_ENGINE,
    name="docker",
    allowed_actions=("docker_prune_dangling",),
)
SSH = ManagedResource(
    id="svc:ssh",
    kind=ResourceKind.SYSTEMD_UNIT,
    name="ssh.service",
    allowed_actions=("stop_service",),
)
TEMPLATED = ManagedResource(
    id="job:backup",
    kind=ResourceKind.BATCH_UNIT,
    name="backup@daily.service",
    allowed_actions=("stop_service",),
)
HIDDEN_DIR = ManagedResource(
    id="dir:.cache",
    kind=ResourceKind.DIRECTORY,
    name="/root/.cache",
    allowed_actions=("clean_temp_dir",),
)


class RecordingRunner:
    def __init__(self, systemctl: FakeSystemctl, after_state: str, returncode: int = 0) -> None:
        self.systemctl = systemctl
        self.after_state = after_state
        self.returncode = returncode
        self.calls: list[tuple[tuple[str, ...], int]] = []

    def run(self, argv: tuple[str, ...], timeout_seconds: int) -> int:
        self.calls.append((argv, timeout_seconds))
        self.systemctl.active_state = self.after_state
        return self.returncode


def config(tmp_path: Path) -> SentinelConfig:
    return sentinel_config(tmp_path).model_copy(
        update={
            "actions": ActionsConfig(enabled=True),
            "resources": [REPORT_JOB, DEMO_DATA, JOURNAL, DOCKER, SSH, TEMPLATED, HIDDEN_DIR],
        }
    )


def request(action_type: ActionType, resource_id: str) -> ActionRequest:
    return ActionRequest(
        action_id=uuid4(),
        attempt_id=uuid4(),
        incident_id=INCIDENT,
        attempt=1,
        action_hash=compute_action_hash(action_type, "demo-1", resource_id, {}, INCIDENT, 1),
        resource_id=resource_id,
        auto_policy_ref="policy:test",
    )


def executor(
    tmp_path: Path, before: str = "active", after: str = "inactive", returncode: int = 0
) -> tuple[ActionExecutor, RecordingRunner]:
    systemctl = FakeSystemctl(active_state=before)
    runner = RecordingRunner(systemctl, after, returncode)
    store = ActionStore(tmp_path / "actions.db")
    return (
        ActionExecutor(config(tmp_path), systemctl, runner, store, lambda: NOW, lambda _: None),
        runner,
    )


@pytest.mark.parametrize(
    ("action_type", "resource", "unit"),
    [
        ("stop_service", REPORT_JOB, "noc-action-stop-service@noc-chaos-cpu-burn.service.service"),
        ("throttle_cpu", REPORT_JOB, "noc-action-throttle-cpu@noc-chaos-cpu-burn.service.service"),
        ("rotate_logs", DEMO_DATA, "noc-action-rotate-logs@demo-data.service"),
        ("clean_temp_dir", DEMO_DATA, "noc-action-clean-temp-dir@demo-data.service"),
        ("vacuum_journal", JOURNAL, "noc-action-vacuum-journal.service"),
        ("docker_prune_dangling", DOCKER, "noc-action-docker-prune-dangling.service"),
    ],
)
def test_each_host_action_starts_its_own_fixed_unit(
    action_type: ActionType, resource: ManagedResource, unit: str, tmp_path: Path
) -> None:
    run, runner = executor(tmp_path)
    outcome = run.execute(action_type, request(action_type, resource.id))
    assert outcome.result.status == "succeeded"
    assert [argv for argv, _ in runner.calls] == [(SYSTEMCTL, "start", unit)]


def test_the_runner_gets_the_action_timeout_plus_a_margin(tmp_path: Path) -> None:
    run, runner = executor(tmp_path)
    run.execute("rotate_logs", request("rotate_logs", DEMO_DATA.id))
    assert runner.calls[0][1] == HOST_ACTIONS["rotate_logs"].timeout_seconds + 15


def test_stop_records_the_unit_state_before_and_after(tmp_path: Path) -> None:
    run, _ = executor(tmp_path, before="active", after="inactive")
    result = run.execute("stop_service", request("stop_service", REPORT_JOB.id)).result
    assert result.status == "succeeded"
    assert result.message == "unit is stopped"
    assert result.before is not None
    assert result.before.active_state == "active"
    assert result.after is not None
    assert result.after.active_state == "inactive"


def test_a_unit_still_running_after_the_stop_is_a_failure(tmp_path: Path) -> None:
    run, _ = executor(tmp_path, before="active", after="active")
    result = run.execute("stop_service", request("stop_service", REPORT_JOB.id)).result
    assert result.status == "failed"
    assert result.code == "STILL_RUNNING"


def test_directory_actions_carry_no_unit_status(tmp_path: Path) -> None:
    run, _ = executor(tmp_path)
    result = run.execute("rotate_logs", request("rotate_logs", DEMO_DATA.id)).result
    assert result.status == "succeeded"
    assert result.message == "host action finished"
    assert result.before is None
    assert result.after is None


def test_a_script_that_refuses_is_a_failed_action(tmp_path: Path) -> None:
    run, _ = executor(tmp_path, returncode=3)
    result = run.execute("clean_temp_dir", request("clean_temp_dir", DEMO_DATA.id)).result
    assert result.status == "failed"
    assert result.code == "EXIT_3"


def test_a_host_action_on_the_wrong_resource_kind_is_refused(tmp_path: Path) -> None:
    run, runner = executor(tmp_path)
    outcome = run.execute("rotate_logs", request("rotate_logs", REPORT_JOB.id))
    assert outcome.status_code == 403
    assert outcome.result.code == "NOT_ALLOWED"
    assert runner.calls == []


def test_protected_units_cannot_be_stopped(tmp_path: Path) -> None:
    run, runner = executor(tmp_path)
    outcome = run.execute("stop_service", request("stop_service", SSH.id))
    assert outcome.result.code == "PROTECTED"
    assert runner.calls == []


@pytest.mark.parametrize("resource", [TEMPLATED, HIDDEN_DIR])
def test_names_that_cannot_be_a_unit_instance_are_refused(
    resource: ManagedResource, tmp_path: Path
) -> None:
    action_type: HostActionType = (
        "stop_service" if resource.kind is ResourceKind.BATCH_UNIT else "clean_temp_dir"
    )
    run, runner = executor(tmp_path)
    outcome = run.execute(action_type, request(action_type, resource.id))
    assert outcome.status_code == 403
    assert outcome.result.code == "BAD_RESOURCE_NAME"
    assert runner.calls == []
    assert host_action_unit(action_type, resource) is None


@pytest.mark.parametrize(
    ("cgroup", "unit"),
    [
        ("0::/system.slice/noc-chaos-cpu-burn.service\n", "noc-chaos-cpu-burn.service"),
        ("0::/user.slice/user-1000.slice/session-3.scope\n", None),
        ("0::/system.slice/demo-shop.service/worker\n", "demo-shop.service"),
        ("", None),
    ],
)
def test_the_unit_of_a_process_comes_from_its_cgroup(cgroup: str, unit: str | None) -> None:
    assert unit_from_cgroup(cgroup) == unit
