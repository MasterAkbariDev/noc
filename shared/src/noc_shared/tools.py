from enum import StrEnum
from typing import Any, Literal

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


class NoArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


ProcessSort = Literal["cpu", "memory"]


class TopProcessesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sort_by: ProcessSort = "cpu"
    limit: int = Field(10, ge=1, le=15)


class CpuUsage(BaseModel):
    percent: float
    per_core_percent: list[float]
    steal_percent: float
    iowait_percent: float
    load_1m: float
    load_5m: float
    load_15m: float


class MemoryUsage(BaseModel):
    total_bytes: int
    used_bytes: int
    available_bytes: int
    cached_bytes: int | None
    swap_total_bytes: int
    swap_used_bytes: int


class MountUsage(BaseModel):
    mountpoint: str
    device: str
    fstype: str
    total_bytes: int
    used_bytes: int
    free_bytes: int
    percent: float
    inodes_total: int
    inodes_used: int


class DiskUsage(BaseModel):
    mounts: list[MountUsage]


class ProcessInfo(BaseModel):
    pid: int
    name: str
    user: str
    cpu_percent: float
    rss_bytes: int
    started_at: str
    cmdline: str


class TopProcesses(BaseModel):
    sort_by: ProcessSort
    processes: list[ProcessInfo]


JournalPriority = Literal["debug", "info", "warning", "err", "crit"]


class GetServiceLogsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId = Field(
        description="Id of a registered systemd unit, e.g. svc:demo-shop"
    )
    since_minutes: int = Field(15, ge=1, le=60)
    max_lines: int = Field(100, ge=1, le=200)
    min_priority: JournalPriority = "warning"


class LogLine(BaseModel):
    ts: str | None
    priority: int | None
    message: str


class ServiceLogs(BaseModel):
    resource_id: str
    unit: str
    lines: list[LogLine]
    truncated: bool


class PathSize(BaseModel):
    path: str
    size_bytes: int


class RootSize(BaseModel):
    path: str
    total_bytes: int | None
    readable: bool
    largest_children: list[PathSize]
    largest_files: list[PathSize]


class DirectorySizes(BaseModel):
    roots: list[RootSize]
    complete: bool
    scanned_entries: int
