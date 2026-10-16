import hashlib
import json
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from noc_shared.resources import ResourceId
from noc_shared.tools import ServiceStatus

ServiceActionType = Literal["start_service", "restart_service"]
HostActionType = Literal[
    "stop_service",
    "throttle_cpu",
    "limit_memory",
    "vacuum_journal",
    "rotate_logs",
    "clean_temp_dir",
    "docker_prune_dangling",
]
ActionType = ServiceActionType | HostActionType
ActionStatus = Literal["executing", "succeeded", "failed", "refused"]
ActionHash = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
AutoPolicyRef = Annotated[str, StringConstraints(max_length=80)]
ActionParams = dict[str, str | int]


class ActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: UUID
    attempt_id: UUID
    incident_id: UUID
    attempt: int = Field(ge=1, le=10)
    action_hash: ActionHash
    resource_id: ResourceId
    params: ActionParams = Field(default_factory=dict)
    approval_id: UUID | None = None
    auto_policy_ref: AutoPolicyRef | None = None

    @model_validator(mode="after")
    def check_exactly_one_authority(self) -> Self:
        if (self.approval_id is None) == (self.auto_policy_ref is None):
            raise ValueError("exactly one of approval_id or auto_policy_ref is required")
        return self


class ActionResult(BaseModel):
    action_id: UUID
    action_type: ActionType
    resource_id: str
    status: ActionStatus
    code: str | None
    message: str = Field(max_length=300)
    started_at: datetime
    finished_at: datetime | None
    before: ServiceStatus | None
    after: ServiceStatus | None
    deduplicated: bool = False


def compute_action_hash(
    action_type: str,
    target: str,
    resource_id: str,
    params: ActionParams,
    incident_id: UUID,
    attempt: int,
) -> str:
    canonical = json.dumps(
        {
            "action_type": action_type,
            "target": target,
            "resource_id": resource_id,
            "params": params,
            "incident_id": str(incident_id),
            "attempt": attempt,
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode()).hexdigest()
