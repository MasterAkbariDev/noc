import json
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from pydantic import ValidationError

from noc.policy.models import ActionCheck
from noc.tools.registry import ToolRegistry
from noc.tools.spec import ToolContext
from noc_shared.tools import CpuUsage, DiskUsage, MemoryUsage, MountUsage

MIN_FREE_RATIO = 0.10
MAX_CPU_PERCENT = 90.0
MIN_AVAILABLE_MEMORY_RATIO = 0.10
STOPPED_STATES = frozenset({"inactive", "failed"})

CHECK_TOOLS: dict[ActionCheck, str] = {
    ActionCheck.SERVICE_ACTIVE: "get_service_status",
    ActionCheck.SERVICE_INACTIVE: "get_service_status",
    ActionCheck.DISK_FREE: "get_disk_usage",
    ActionCheck.CPU_RELIEVED: "get_cpu_usage",
    ActionCheck.MEMORY_RELIEVED: "get_memory_usage",
}
SERVICE_CHECKS = frozenset({ActionCheck.SERVICE_ACTIVE, ActionCheck.SERVICE_INACTIVE})


@dataclass(frozen=True)
class CheckReading:
    ok: bool
    passed: bool
    active_state: str | None = None
    error: str | None = None


def check_arguments(check: ActionCheck, resource_id: str) -> dict[str, str]:
    return {"resource_id": resource_id} if check in SERVICE_CHECKS else {}


def mount_for(path: str, mounts: list[MountUsage]) -> MountUsage | None:
    target = PurePosixPath(path)
    containing = [
        mount
        for mount in mounts
        if target == PurePosixPath(mount.mountpoint)
        or PurePosixPath(mount.mountpoint) in target.parents
    ]
    return max(containing, key=lambda mount: len(mount.mountpoint), default=None)


def disk_has_room(data: dict[str, Any], path: str) -> bool:
    mount = mount_for(path, DiskUsage.model_validate(data).mounts)
    if mount is None or mount.total_bytes <= 0:
        return False
    return mount.free_bytes / mount.total_bytes > MIN_FREE_RATIO


def cpu_relieved(data: dict[str, Any]) -> bool:
    return CpuUsage.model_validate(data).percent < MAX_CPU_PERCENT


def memory_relieved(data: dict[str, Any]) -> bool:
    memory = MemoryUsage.model_validate(data)
    return memory.total_bytes > 0 and (
        memory.available_bytes / memory.total_bytes >= MIN_AVAILABLE_MEMORY_RATIO
    )


def passes(check: ActionCheck, data: dict[str, Any], resource_name: str) -> bool:
    state = str(data.get("active_state"))
    if check is ActionCheck.SERVICE_ACTIVE:
        return state == "active"
    if check is ActionCheck.SERVICE_INACTIVE:
        return state in STOPPED_STATES
    if check is ActionCheck.DISK_FREE:
        return disk_has_room(data, resource_name)
    if check is ActionCheck.CPU_RELIEVED:
        return cpu_relieved(data)
    if check is ActionCheck.MEMORY_RELIEVED:
        return memory_relieved(data)
    return True


def reading_from(check: ActionCheck, data: dict[str, Any], resource_name: str) -> CheckReading:
    try:
        passed = passes(check, data, resource_name)
    except ValidationError:
        return CheckReading(ok=False, passed=False, error="the tool answer had an unexpected shape")
    state = data.get("active_state") if check in SERVICE_CHECKS else None
    return CheckReading(ok=True, passed=passed, active_state=None if state is None else str(state))


async def read_check(
    registry: ToolRegistry,
    context: ToolContext,
    check: ActionCheck,
    resource_id: str,
    resource_name: str,
) -> CheckReading:
    tool = CHECK_TOOLS.get(check)
    if tool is None:
        return CheckReading(ok=True, passed=True)
    arguments = json.dumps(check_arguments(check, resource_id))
    result = await registry.execute(tool, arguments, context)
    if not result.ok or result.data is None:
        return CheckReading(ok=False, passed=False, error=result.content[:300])
    return reading_from(check, result.data, resource_name)
