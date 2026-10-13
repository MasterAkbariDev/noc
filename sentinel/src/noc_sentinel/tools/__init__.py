import subprocess
import time
from collections.abc import Callable
from typing import Any

import psutil
from pydantic import BaseModel, ValidationError

from noc_sentinel.config import SENTINEL_VERSION, SentinelConfig
from noc_sentinel.tools.auth import (
    AUTH_LINES_MAX,
    AuthLogReader,
    SessionReader,
    active_sessions,
    auth_events,
)
from noc_sentinel.tools.disk_breakdown import DiskBreakdownReader
from noc_sentinel.tools.host import HostReader
from noc_sentinel.tools.journal import JournalReader
from noc_sentinel.tools.network import NetworkReader
from noc_sentinel.tools.systemd import SystemctlRunner, read_service_status
from noc_shared.resources import ManagedResource, ResourceKind
from noc_shared.tools import (
    GetAuthEventsArgs,
    GetServiceLogsArgs,
    GetServiceStatusArgs,
    NoArgs,
    ServiceLogs,
    ToolCallResponse,
    ToolError,
    ToolErrorCode,
    TopProcesses,
    TopProcessesArgs,
)

RawArgs = dict[str, Any]
ToolHandler = Callable[[RawArgs], dict[str, Any]]


class ToolFailure(Exception):
    def __init__(self, code: ToolErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


def parse_args[ArgsT: BaseModel](model: type[ArgsT], raw_args: RawArgs) -> ArgsT:
    try:
        return model.model_validate(raw_args)
    except ValidationError as exc:
        raise ToolFailure(ToolErrorCode.VALIDATION, exc.errors()[0]["msg"]) from exc


class Toolbox:
    def __init__(
        self,
        config: SentinelConfig,
        systemctl: SystemctlRunner,
        host: HostReader,
        journal: JournalReader,
        disk_breakdown: DiskBreakdownReader,
        network: NetworkReader,
        auth_log: AuthLogReader,
        sessions: SessionReader,
    ) -> None:
        self._config = config
        self._systemctl = systemctl
        self._host = host
        self._journal = journal
        self._disk_breakdown = disk_breakdown
        self._network = network
        self._auth_log = auth_log
        self._sessions = sessions
        self._tools: dict[str, ToolHandler] = {
            "get_service_status": self._get_service_status,
            "get_service_logs": self._get_service_logs,
            "get_cpu_usage": self._get_cpu_usage,
            "get_memory_usage": self._get_memory_usage,
            "get_disk_usage": self._get_disk_usage,
            "get_top_processes": self._get_top_processes,
            "get_directory_sizes": self._get_directory_sizes,
            "get_listening_ports": self._get_listening_ports,
            "get_network_stats": self._get_network_stats,
            "get_connection_summary": self._get_connection_summary,
            "get_auth_events": self._get_auth_events,
            "get_active_sessions": self._get_active_sessions,
        }

    def names(self) -> list[str]:
        return sorted(self._tools)

    def run(self, name: str, raw_args: RawArgs) -> ToolCallResponse:
        started = time.monotonic()
        try:
            response = ToolCallResponse(ok=True, data=self._dispatch(name, raw_args))
        except ToolFailure as failure:
            error = ToolError(code=failure.code, message=str(failure))
            response = ToolCallResponse(ok=False, error=error)
        response.duration_ms = int((time.monotonic() - started) * 1000)
        response.sentinel_version = SENTINEL_VERSION
        return response

    def _dispatch(self, name: str, raw_args: RawArgs) -> dict[str, Any]:
        handler = self._tools.get(name)
        if handler is None:
            raise ToolFailure(ToolErrorCode.NOT_FOUND, f"unknown tool {name}")
        try:
            return handler(raw_args)
        except subprocess.TimeoutExpired as exc:
            raise ToolFailure(ToolErrorCode.TIMEOUT, "system call timed out") from exc
        except (subprocess.CalledProcessError, OSError, psutil.Error) as exc:
            raise ToolFailure(ToolErrorCode.INTERNAL, type(exc).__name__) from exc

    def _registered(self, resource_id: str, kind: ResourceKind) -> ManagedResource:
        resource = self._config.resource(resource_id)
        if resource is None:
            raise ToolFailure(ToolErrorCode.NOT_FOUND, f"resource {resource_id} is not registered")
        if resource.kind != kind:
            raise ToolFailure(ToolErrorCode.NOT_ALLOWED, f"resource {resource_id} is not a {kind}")
        return resource

    def _get_service_status(self, raw_args: RawArgs) -> dict[str, Any]:
        args = parse_args(GetServiceStatusArgs, raw_args)
        resource = self._registered(args.resource_id, ResourceKind.SYSTEMD_UNIT)
        return read_service_status(resource, self._systemctl).model_dump()

    def _get_service_logs(self, raw_args: RawArgs) -> dict[str, Any]:
        args = parse_args(GetServiceLogsArgs, raw_args)
        resource = self._registered(args.resource_id, ResourceKind.SYSTEMD_UNIT)
        lines = self._journal.read(
            resource.name, args.since_minutes, args.max_lines, args.min_priority
        )
        return ServiceLogs(
            resource_id=resource.id,
            unit=resource.name,
            lines=lines,
            truncated=len(lines) >= args.max_lines,
        ).model_dump()

    def _get_cpu_usage(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return self._host.cpu().model_dump()

    def _get_memory_usage(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return self._host.memory().model_dump()

    def _get_disk_usage(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return self._host.disks().model_dump()

    def _get_top_processes(self, raw_args: RawArgs) -> dict[str, Any]:
        args = parse_args(TopProcessesArgs, raw_args)
        processes = self._host.processes(args.sort_by, args.limit)
        return TopProcesses(sort_by=args.sort_by, processes=processes).model_dump()

    def _get_directory_sizes(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return self._disk_breakdown.directory_sizes(self._config.disk_breakdown_roots).model_dump()

    def _get_listening_ports(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return self._network.listening_ports().model_dump()

    def _get_network_stats(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return self._network.stats().model_dump()

    def _get_connection_summary(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return self._network.connections().model_dump()

    def _get_auth_events(self, raw_args: RawArgs) -> dict[str, Any]:
        args = parse_args(GetAuthEventsArgs, raw_args)
        sshd_lines = self._auth_log.read("sshd", args.since_minutes, AUTH_LINES_MAX)
        sudo_lines = self._auth_log.read("sudo", args.since_minutes, AUTH_LINES_MAX)
        return auth_events(sshd_lines, sudo_lines).model_dump()

    def _get_active_sessions(self, raw_args: RawArgs) -> dict[str, Any]:
        parse_args(NoArgs, raw_args)
        return active_sessions(self._sessions.sessions()).model_dump()
