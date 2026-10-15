import json
import re
import shutil
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Literal, Protocol

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from noc_sentinel.config import SentinelConfig
from noc_sentinel.halt import is_halted
from noc_sentinel.security import RequestVerifier
from noc_shared.resources import ManagedResource, ResourceId, ResourceKind
from noc_shared.signing import VerifiedRequest

SYSTEMCTL_PATH = "/usr/bin/systemctl"
SYSTEMD_RUN_PATH = "/usr/bin/systemd-run"
FALLOCATE_PATH = "/usr/bin/fallocate"
RM_PATH = "/usr/bin/rm"
YES_PATH = "/usr/bin/yes"
BASH_PATH = "/bin/bash"
CURL_PATH = "/usr/bin/curl"
APP_CHAOS_HOST = "127.0.0.1"
APP_FAULT = "app-fault"
RESTORE_UNIT_PREFIX = "noc-chaos-restore-"
CPU_BURN_UNIT = "noc-chaos-cpu-burn"
CPU_BURN_RESTORE_UNIT = "noc-chaos-restore-cpu-burn"
CPU_BURN_PROCESS_NAME = "report-gen"
DISK_FILL_FILE_NAME = "noc-chaos-fill.log"
DISK_FILL_RESTORE_UNIT = "noc-chaos-restore-disk-fill"
SERVICE_DOWN = "service-down"
CPU_BURN = "cpu-burn"
DISK_FILL = "disk-fill"
CHAOS_ACTION = "chaos_service_down"
CHAOS_TIMEOUT_SECONDS = 10


class ChaosRunner(Protocol):
    def run(self, argv: tuple[str, ...]) -> int: ...


class SubprocessChaosRunner:
    def run(self, argv: tuple[str, ...]) -> int:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=CHAOS_TIMEOUT_SECONDS,
            check=False,
        )
        return completed.returncode


class EmptyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ServiceDownStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId
    ttl_seconds: int = Field(ge=1)


class ServiceDownStop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId


class CpuBurnStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    workers: int = Field(ge=1, le=8)
    ttl_seconds: int = Field(ge=1)


class DiskFillStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_percent: int = Field(ge=50, le=95)
    ttl_seconds: int = Field(ge=1)


AppFault = Literal["memory_leak", "upstream_delay", "connection_leak"]


class AppFaultStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId
    fault: AppFault
    ttl_seconds: int = Field(ge=1)


class AppFaultStop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId


class ChaosStatus(BaseModel):
    active: bool
    scenario: str | None = None
    fault: str | None = None
    resource_id: str | None = None
    unit: str | None = None
    started_at: datetime | None = None
    expires_at: datetime | None = None


class ChaosFailure(Exception):
    def __init__(self, status_code: int, code: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code


@dataclass(frozen=True)
class ActiveChaos:
    scenario: str
    restore_unit: str
    undo_argv: tuple[str, ...]
    started_at: datetime
    expires_at: datetime
    resource_id: str | None = None
    unit: str | None = None
    fault: str | None = None


def restore_unit_name(unit: str) -> str:
    return RESTORE_UNIT_PREFIX + re.sub(r"[^A-Za-z0-9-]", "-", unit)


def stop_unit_argv(unit: str) -> tuple[str, ...]:
    return (SYSTEMCTL_PATH, "stop", unit)


def start_unit_argv(unit: str) -> tuple[str, ...]:
    return (SYSTEMCTL_PATH, "start", unit)


def schedule_restore_argv(
    restore_unit: str, command: tuple[str, ...], ttl_seconds: int
) -> tuple[str, ...]:
    return (SYSTEMD_RUN_PATH, f"--unit={restore_unit}", f"--on-active={ttl_seconds}", *command)


def stop_restore_timer_argv(restore_unit: str) -> tuple[str, ...]:
    return (SYSTEMCTL_PATH, "stop", f"{restore_unit}.timer")


def cpu_burn_start_argv(workers: int, ttl_seconds: int) -> tuple[str, ...]:
    script = (
        f"for i in $(seq {workers}); do "
        f"(exec -a {CPU_BURN_PROCESS_NAME} {YES_PATH} > /dev/null) & done; wait"
    )
    return (
        SYSTEMD_RUN_PATH,
        f"--unit={CPU_BURN_UNIT}",
        f"--property=RuntimeMaxSec={ttl_seconds}",
        "--property=Nice=0",
        BASH_PATH,
        "-c",
        script,
    )


def stop_cpu_burn_argv() -> tuple[str, ...]:
    return stop_unit_argv(CPU_BURN_UNIT)


def fill_file_path(directory: Path) -> Path:
    return directory / DISK_FILL_FILE_NAME


def fallocate_argv(path: Path, size_bytes: int) -> tuple[str, ...]:
    return (FALLOCATE_PATH, "-l", str(size_bytes), str(path))


def remove_fill_argv(path: Path) -> tuple[str, ...]:
    return (RM_PATH, "-f", str(path))


def app_chaos_url(port: int) -> str:
    return f"http://{APP_CHAOS_HOST}:{port}/chaos"


def app_fault_body(fault: AppFault, upstream_delay_ms: int) -> str:
    settings: dict[str, bool | int] = (
        {"upstream_delay_ms": upstream_delay_ms} if fault == "upstream_delay" else {fault: True}
    )
    return json.dumps(settings, sort_keys=True)


def set_app_fault_argv(port: int, body: str) -> tuple[str, ...]:
    return (
        CURL_PATH,
        "-fsS",
        "--max-time",
        "5",
        "-X",
        "PUT",
        "-H",
        "Content-Type: application/json",
        "--data",
        body,
        app_chaos_url(port),
    )


def reset_app_fault_argv(port: int) -> tuple[str, ...]:
    return (CURL_PATH, "-fsS", "--max-time", "5", "-X", "POST", app_chaos_url(port) + "/reset")


def fill_bytes(total: int, used: int, available: int, target_percent: int, min_free: int) -> int:
    toward_target = total * target_percent // 100 - used
    keeping_free = available - min_free
    return min(toward_target, keeping_free)


class ChaosController:
    def __init__(
        self,
        config: SentinelConfig,
        runner: ChaosRunner,
        clock: Callable[[], datetime],
    ) -> None:
        self._config = config
        self._runner = runner
        self._clock = clock
        self._active: ActiveChaos | None = None
        self._lock = threading.Lock()

    def status(self) -> ChaosStatus:
        with self._lock:
            self._expire(self._clock())
            return status_of(self._active)

    def start(self, resource_id: str, ttl_seconds: int) -> ChaosStatus:
        self._check_ttl(ttl_seconds)
        resource = self._service_resource(resource_id)
        with self._lock:
            now = self._clock()
            self._claim_slot(now)
            unit = resource.name
            restore_unit = restore_unit_name(unit)
            active = ActiveChaos(
                scenario=SERVICE_DOWN,
                restore_unit=restore_unit,
                undo_argv=start_unit_argv(unit),
                started_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                resource_id=resource.id,
                unit=unit,
            )
            return self._launch(
                active,
                schedule_restore_argv(restore_unit, start_unit_argv(unit), ttl_seconds),
                stop_unit_argv(unit),
                None,
            )

    def stop(self, resource_id: str) -> ChaosStatus:
        return self._stop_scenario(SERVICE_DOWN, resource_id)

    def start_cpu_burn(self, workers: int, ttl_seconds: int) -> ChaosStatus:
        self._check_ttl(ttl_seconds)
        with self._lock:
            now = self._clock()
            self._claim_slot(now)
            active = ActiveChaos(
                scenario=CPU_BURN,
                restore_unit=CPU_BURN_RESTORE_UNIT,
                undo_argv=stop_cpu_burn_argv(),
                started_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                unit=CPU_BURN_UNIT,
            )
            return self._launch(
                active,
                schedule_restore_argv(CPU_BURN_RESTORE_UNIT, stop_cpu_burn_argv(), ttl_seconds),
                cpu_burn_start_argv(workers, ttl_seconds),
                stop_cpu_burn_argv(),
            )

    def stop_cpu_burn(self) -> ChaosStatus:
        return self._stop_scenario(CPU_BURN, None)

    def start_disk_fill(self, target_percent: int, ttl_seconds: int) -> ChaosStatus:
        self._check_ttl(ttl_seconds)
        with self._lock:
            now = self._clock()
            self._claim_slot(now)
            directory = self._fill_directory()
            size = self._fill_size(directory, target_percent)
            path = fill_file_path(directory)
            active = ActiveChaos(
                scenario=DISK_FILL,
                restore_unit=DISK_FILL_RESTORE_UNIT,
                undo_argv=remove_fill_argv(path),
                started_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            return self._launch(
                active,
                schedule_restore_argv(DISK_FILL_RESTORE_UNIT, remove_fill_argv(path), ttl_seconds),
                fallocate_argv(path, size),
                remove_fill_argv(path),
            )

    def stop_disk_fill(self) -> ChaosStatus:
        return self._stop_scenario(DISK_FILL, None)

    def start_app_fault(self, resource_id: str, fault: AppFault, ttl_seconds: int) -> ChaosStatus:
        self._check_ttl(ttl_seconds)
        port = self._app_port(resource_id)
        with self._lock:
            now = self._clock()
            self._claim_slot(now)
            restore_unit = restore_unit_name(f"app-{resource_id}")
            reset = reset_app_fault_argv(port)
            active = ActiveChaos(
                scenario=APP_FAULT,
                restore_unit=restore_unit,
                undo_argv=reset,
                started_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
                resource_id=resource_id,
                fault=fault,
            )
            body = app_fault_body(fault, self._config.chaos.upstream_delay_ms)
            return self._launch(
                active,
                schedule_restore_argv(restore_unit, reset, ttl_seconds),
                set_app_fault_argv(port, body),
                reset,
            )

    def stop_app_fault(self, resource_id: str) -> ChaosStatus:
        return self._stop_scenario(APP_FAULT, resource_id)

    def _app_port(self, resource_id: str) -> int:
        if self._config.resource(resource_id) is None:
            raise ChaosFailure(404, "NOT_FOUND")
        port = self._config.chaos.app_chaos_ports.get(resource_id)
        if port is None:
            raise ChaosFailure(403, "NOT_ALLOWED")
        return port

    def _check_ttl(self, ttl_seconds: int) -> None:
        if ttl_seconds > self._config.chaos.max_ttl_seconds:
            raise ChaosFailure(422, "VALIDATION")

    def _claim_slot(self, now: datetime) -> None:
        self._expire(now)
        if self._active is not None:
            raise ChaosFailure(409, "ALREADY_ACTIVE")
        if is_halted(self._config.halt_file):
            raise ChaosFailure(409, "HALTED")

    def _launch(
        self,
        active: ActiveChaos,
        restore_argv: tuple[str, ...],
        inject_argv: tuple[str, ...],
        rollback_argv: tuple[str, ...] | None,
    ) -> ChaosStatus:
        self._execute(restore_argv)
        try:
            self._execute(inject_argv)
        except ChaosFailure:
            if rollback_argv is not None:
                self._best_effort(rollback_argv)
            self._best_effort(stop_restore_timer_argv(active.restore_unit))
            raise
        self._active = active
        return status_of(active)

    def _stop_scenario(self, scenario: str, resource_id: str | None) -> ChaosStatus:
        with self._lock:
            self._expire(self._clock())
            active = self._active
            if active is None or active.scenario != scenario or active.resource_id != resource_id:
                raise ChaosFailure(409, "NOT_ACTIVE")
            self._execute(active.undo_argv)
            self._best_effort(stop_restore_timer_argv(active.restore_unit))
            self._active = None
            return status_of(None)

    def _fill_directory(self) -> Path:
        directory = self._config.chaos.disk_fill_dir
        if directory is None or not directory.is_dir():
            raise ChaosFailure(409, "NOT_CONFIGURED")
        return directory

    def _fill_size(self, directory: Path, target_percent: int) -> int:
        try:
            usage = shutil.disk_usage(directory)
        except OSError as exc:
            raise ChaosFailure(500, "INTERNAL") from exc
        size = fill_bytes(
            usage.total,
            usage.used,
            usage.free,
            target_percent,
            self._config.chaos.disk_fill_min_free_bytes,
        )
        if size <= 0:
            raise ChaosFailure(409, "NOT_POSSIBLE")
        return size

    def _service_resource(self, resource_id: str) -> ManagedResource:
        resource = self._config.resource(resource_id)
        if resource is None:
            raise ChaosFailure(404, "NOT_FOUND")
        if (
            resource.kind != ResourceKind.SYSTEMD_UNIT
            or CHAOS_ACTION not in resource.allowed_actions
        ):
            raise ChaosFailure(403, "NOT_ALLOWED")
        return resource

    def _expire(self, now: datetime) -> None:
        if self._active is not None and now >= self._active.expires_at:
            self._active = None

    def _execute(self, argv: tuple[str, ...]) -> None:
        try:
            returncode = self._runner.run(argv)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ChaosFailure(500, "INTERNAL") from exc
        if returncode != 0:
            raise ChaosFailure(500, "INTERNAL")

    def _best_effort(self, argv: tuple[str, ...]) -> None:
        try:
            self._runner.run(argv)
        except (OSError, subprocess.SubprocessError):
            return


def status_of(active: ActiveChaos | None) -> ChaosStatus:
    if active is None:
        return ChaosStatus(active=False)
    return ChaosStatus(
        active=True,
        scenario=active.scenario,
        resource_id=active.resource_id,
        unit=active.unit,
        fault=active.fault,
        started_at=active.started_at,
        expires_at=active.expires_at,
    )


def run_guarded(action: Callable[[], ChaosStatus]) -> ChaosStatus:
    try:
        return action()
    except ChaosFailure as failure:
        raise HTTPException(failure.status_code, failure.code) from failure


def build_chaos_router(controller: ChaosController, verifier: RequestVerifier) -> APIRouter:
    router = APIRouter(prefix="/v1/chaos")
    Signed = Annotated[VerifiedRequest, Depends(verifier)]

    @router.get("/status")
    def status(_: Signed) -> ChaosStatus:
        return controller.status()

    @router.post("/service-down/start")
    def start_service_down(request: ServiceDownStart, _: Signed) -> ChaosStatus:
        return run_guarded(lambda: controller.start(request.resource_id, request.ttl_seconds))

    @router.post("/service-down/stop")
    def stop_service_down(request: ServiceDownStop, _: Signed) -> ChaosStatus:
        return run_guarded(lambda: controller.stop(request.resource_id))

    @router.post("/cpu-burn/start")
    def start_cpu_burn(request: CpuBurnStart, _: Signed) -> ChaosStatus:
        return run_guarded(lambda: controller.start_cpu_burn(request.workers, request.ttl_seconds))

    @router.post("/cpu-burn/stop")
    def stop_cpu_burn(_body: EmptyRequest, _: Signed) -> ChaosStatus:
        return run_guarded(controller.stop_cpu_burn)

    @router.post("/disk-fill/start")
    def start_disk_fill(request: DiskFillStart, _: Signed) -> ChaosStatus:
        return run_guarded(
            lambda: controller.start_disk_fill(request.target_percent, request.ttl_seconds)
        )

    @router.post("/app-fault/start")
    def start_app_fault(request: AppFaultStart, _: Signed) -> ChaosStatus:
        return run_guarded(
            lambda: controller.start_app_fault(
                request.resource_id, request.fault, request.ttl_seconds
            )
        )

    @router.post("/app-fault/stop")
    def stop_app_fault(request: AppFaultStop, _: Signed) -> ChaosStatus:
        return run_guarded(lambda: controller.stop_app_fault(request.resource_id))

    @router.post("/disk-fill/stop")
    def stop_disk_fill(_body: EmptyRequest, _: Signed) -> ChaosStatus:
        return run_guarded(controller.stop_disk_fill)

    return router
