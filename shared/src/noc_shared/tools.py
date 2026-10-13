from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from noc_shared.resources import ResourceId


class ToolErrorCode(StrEnum):
    VALIDATION = "VALIDATION"
    NOT_ALLOWED = "NOT_ALLOWED"
    NOT_FOUND = "NOT_FOUND"
    TIMEOUT = "TIMEOUT"
    HALTED = "HALTED"
    INTERNAL = "INTERNAL"


class ToolError(BaseModel):
    code: ToolErrorCode
    message: str


class ToolCallRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    args: dict[str, Any] = Field(default_factory=dict)
    incident_id: str | None = None


class ToolCallResponse(BaseModel):
    ok: bool
    data: dict[str, Any] | None = None
    error: ToolError | None = None
    truncated: bool = False
    duration_ms: int = 0
    sentinel_version: str = ""


class GetServiceStatusArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId = Field(
        description="Id of a registered systemd unit, e.g. svc:demo-shop"
    )


class ServiceStatus(BaseModel):
    resource_id: str
    unit: str
    active_state: str
    sub_state: str
    restarts: int | None
    exec_main_status: int | None
    active_since: str | None
    memory_bytes: int | None
