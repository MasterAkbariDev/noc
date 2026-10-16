import re
from dataclasses import dataclass
from typing import TypeGuard

from noc_shared.actions import HostActionType
from noc_shared.resources import ManagedResource, ResourceKind

ACTION_UNIT_PREFIX = "noc-action-"
INSTANCE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
UNIT_KINDS = frozenset({ResourceKind.SYSTEMD_UNIT, ResourceKind.BATCH_UNIT})
UNIT_TIMEOUT_MARGIN_SECONDS = 15


@dataclass(frozen=True)
class HostActionSpec:
    script: str
    kinds: frozenset[ResourceKind]
    takes_instance: bool
    timeout_seconds: int


HOST_ACTIONS: dict[HostActionType, HostActionSpec] = {
    "stop_service": HostActionSpec("stop-service", UNIT_KINDS, True, 60),
    "throttle_cpu": HostActionSpec("throttle-cpu", UNIT_KINDS, True, 30),
    "limit_memory": HostActionSpec("limit-memory", UNIT_KINDS, True, 30),
    "vacuum_journal": HostActionSpec(
        "vacuum-journal", frozenset({ResourceKind.LOG_SOURCE}), False, 120
    ),
    "rotate_logs": HostActionSpec("rotate-logs", frozenset({ResourceKind.DIRECTORY}), True, 300),
    "clean_temp_dir": HostActionSpec(
        "clean-temp-dir", frozenset({ResourceKind.DIRECTORY}), True, 300
    ),
    "docker_prune_dangling": HostActionSpec(
        "docker-prune-dangling", frozenset({ResourceKind.DOCKER_ENGINE}), False, 300
    ),
}


def is_host_action(value: str) -> TypeGuard[HostActionType]:
    return value in HOST_ACTIONS


def action_instance(resource: ManagedResource) -> str:
    if resource.kind in UNIT_KINDS:
        return resource.name
    return resource.id.split(":", 1)[1]


def host_action_unit(action_type: HostActionType, resource: ManagedResource) -> str | None:
    spec = HOST_ACTIONS[action_type]
    if not spec.takes_instance:
        return f"{ACTION_UNIT_PREFIX}{spec.script}.service"
    instance = action_instance(resource)
    if not INSTANCE_PATTERN.match(instance):
        return None
    return f"{ACTION_UNIT_PREFIX}{spec.script}@{instance}.service"


def host_action_timeout(action_type: HostActionType) -> int:
    return HOST_ACTIONS[action_type].timeout_seconds + UNIT_TIMEOUT_MARGIN_SECONDS
