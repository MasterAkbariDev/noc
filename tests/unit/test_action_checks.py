from typing import Any, get_args

import pytest

from noc.config import PACKAGE_DIR
from noc.orchestration.action_checks import (
    CHECK_TOOLS,
    check_arguments,
    mount_for,
    reading_from,
)
from noc.policy.loader import load_policy
from noc.policy.models import ActionCheck
from noc_shared.actions import HostActionType, ServiceActionType
from noc_shared.tools import MountUsage

POLICY = load_policy(PACKAGE_DIR / "policy" / "default_policy.yaml")
GIB = 1024**3


def mount(mountpoint: str, total: int, free: int) -> MountUsage:
    return MountUsage(
        mountpoint=mountpoint,
        device="/dev/x",
        fstype="ext4",
        total_bytes=total,
        used_bytes=total - free,
        free_bytes=free,
        percent=round(100 * (total - free) / total, 1),
        inodes_total=1000,
        inodes_used=10,
    )


def disks(*mounts: MountUsage) -> dict[str, Any]:
    return {"mounts": [item.model_dump() for item in mounts]}


def cpu(percent: float) -> dict[str, Any]:
    return {
        "percent": percent,
        "per_core_percent": [percent],
        "steal_percent": 0.0,
        "iowait_percent": 0.0,
        "load_1m": 1.0,
        "load_5m": 1.0,
        "load_15m": 1.0,
    }


def memory(total: int, available: int) -> dict[str, Any]:
    return {
        "total_bytes": total,
        "used_bytes": total - available,
        "available_bytes": available,
        "cached_bytes": None,
        "swap_total_bytes": 0,
        "swap_used_bytes": 0,
    }


def test_every_executable_action_declares_a_check() -> None:
    executable = [*get_args(ServiceActionType), *get_args(HostActionType)]
    for action in executable:
        definition = POLICY.actions[action]
        assert definition.check is not ActionCheck.NONE, action


def test_the_deepest_mount_holding_the_path_is_used() -> None:
    root = mount("/", 30 * GIB, 10 * GIB)
    data = mount("/srv/demo-data", GIB, GIB // 50)
    assert mount_for("/srv/demo-data", [root, data]) == data
    assert mount_for("/srv/demo-data/logs", [root, data]) == data
    assert mount_for("/srv/demo-database", [root, data]) == root


@pytest.mark.parametrize(("free", "passed"), [(GIB // 50, False), (GIB // 2, True)])
def test_disk_free_follows_the_alert_threshold(free: int, passed: bool) -> None:
    data = disks(mount("/", 30 * GIB, 10 * GIB), mount("/srv/demo-data", GIB, free))
    reading = reading_from(ActionCheck.DISK_FREE, data, "/srv/demo-data")
    assert reading.ok
    assert reading.passed is passed


def test_a_disk_check_without_a_matching_mount_fails() -> None:
    reading = reading_from(ActionCheck.DISK_FREE, disks(), "/srv/demo-data")
    assert reading.ok
    assert not reading.passed


@pytest.mark.parametrize(("percent", "passed"), [(99.0, False), (40.0, True)])
def test_cpu_relieved_means_below_ninety_percent(percent: float, passed: bool) -> None:
    assert reading_from(ActionCheck.CPU_RELIEVED, cpu(percent), "").passed is passed


@pytest.mark.parametrize(("available", "passed"), [(GIB // 20, False), (GIB, True)])
def test_memory_relieved_needs_ten_percent_available(available: int, passed: bool) -> None:
    reading = reading_from(ActionCheck.MEMORY_RELIEVED, memory(4 * GIB, available), "")
    assert reading.passed is passed


@pytest.mark.parametrize(
    ("check", "state", "passed"),
    [
        (ActionCheck.SERVICE_ACTIVE, "active", True),
        (ActionCheck.SERVICE_ACTIVE, "failed", False),
        (ActionCheck.SERVICE_INACTIVE, "inactive", True),
        (ActionCheck.SERVICE_INACTIVE, "failed", True),
        (ActionCheck.SERVICE_INACTIVE, "active", False),
    ],
)
def test_service_checks_read_the_active_state(check: ActionCheck, state: str, passed: bool) -> None:
    reading = reading_from(check, {"active_state": state}, "x.service")
    assert reading.passed is passed
    assert reading.active_state == state


def test_an_unexpected_tool_answer_is_not_ok() -> None:
    reading = reading_from(ActionCheck.CPU_RELIEVED, {"percent": "lots"}, "")
    assert not reading.ok
    assert not reading.passed


def test_only_service_checks_send_the_resource_id() -> None:
    assert check_arguments(ActionCheck.SERVICE_INACTIVE, "job:x") == {"resource_id": "job:x"}
    assert check_arguments(ActionCheck.DISK_FREE, "dir:x") == {}
    assert ActionCheck.NONE not in CHECK_TOOLS
