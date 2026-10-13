import subprocess
import time
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ValidationError

from noc_sentinel.config import SENTINEL_VERSION, SentinelConfig
from noc_sentinel.tools.systemd import SystemctlRunner, read_service_status
from noc_shared.resources import ManagedResource, ResourceKind
from noc_shared.tools import (
    GetServiceStatusArgs,
    ToolCallResponse,
    ToolError,
    ToolErrorCode,
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
    def __init__(self, config: SentinelConfig, systemctl: SystemctlRunner) -> None:
        self._config = config
        self._systemctl = systemctl
        self._tools: dict[str, ToolHandler] = {
            "get_service_status": self._get_service_status,
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
        except (subprocess.CalledProcessError, OSError) as exc:
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
