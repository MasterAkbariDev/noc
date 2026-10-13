import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Protocol

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from noc_sentinel.config import SentinelConfig
from noc_sentinel.halt import is_halted
from noc_sentinel.security import RequestVerifier
from noc_shared.resources import ManagedResource, ResourceId, ResourceKind
from noc_shared.signing import VerifiedRequest

SYSTEMCTL_PATH = "/usr/bin/systemctl"
SYSTEMD_RUN_PATH = "/usr/bin/systemd-run"
RESTORE_UNIT_PREFIX = "noc-chaos-restore-"
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


class ServiceDownStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId
    ttl_seconds: int = Field(ge=1)


class ServiceDownStop(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_id: ResourceId


class ChaosStatus(BaseModel):
    active: bool
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
    resource_id: str
    unit: str
    restore_unit: str
    started_at: datetime
    expires_at: datetime


def restore_unit_name(unit: str) -> str:
    return RESTORE_UNIT_PREFIX + re.sub(r"[^A-Za-z0-9-]", "-", unit)


def stop_unit_argv(unit: str) -> tuple[str, ...]:
    return (SYSTEMCTL_PATH, "stop", unit)


def start_unit_argv(unit: str) -> tuple[str, ...]:
    return (SYSTEMCTL_PATH, "start", unit)


def schedule_restore_argv(restore_unit: str, unit: str, ttl_seconds: int) -> tuple[str, ...]:
    return (
        SYSTEMD_RUN_PATH,
        f"--unit={restore_unit}",
        f"--on-active={ttl_seconds}",
        SYSTEMCTL_PATH,
        "start",
        unit,
    )


def stop_restore_timer_argv(restore_unit: str) -> tuple[str, ...]:
    return (SYSTEMCTL_PATH, "stop", f"{restore_unit}.timer")


class ServiceDownChaos:
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
        if ttl_seconds > self._config.chaos.max_ttl_seconds:
            raise ChaosFailure(422, "VALIDATION")
        resource = self._service_resource(resource_id)
        with self._lock:
            now = self._clock()
            self._expire(now)
            if self._active is not None:
                raise ChaosFailure(409, "ALREADY_ACTIVE")
            if is_halted(self._config.halt_file):
                raise ChaosFailure(409, "HALTED")
            active = ActiveChaos(
                resource_id=resource.id,
                unit=resource.name,
                restore_unit=restore_unit_name(resource.name),
                started_at=now,
                expires_at=now + timedelta(seconds=ttl_seconds),
            )
            self._execute(schedule_restore_argv(active.restore_unit, active.unit, ttl_seconds))
            try:
                self._execute(stop_unit_argv(active.unit))
            except ChaosFailure:
                self._best_effort(stop_restore_timer_argv(active.restore_unit))
                raise
            self._active = active
            return status_of(active)

    def stop(self, resource_id: str) -> ChaosStatus:
        with self._lock:
            self._expire(self._clock())
            active = self._active
            if active is None or active.resource_id != resource_id:
                raise ChaosFailure(409, "NOT_ACTIVE")
            self._execute(start_unit_argv(active.unit))
            self._best_effort(stop_restore_timer_argv(active.restore_unit))
            self._active = None
            return status_of(None)

    def _service_resource(self, resource_id: str) -> ManagedResource:
        resource = self._config.resource(resource_id)
        if resource is None:
            raise ChaosFailure(404, "NOT_FOUND")
        if resource.kind != ResourceKind.SYSTEMD_UNIT:
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
        resource_id=active.resource_id,
        unit=active.unit,
        started_at=active.started_at,
        expires_at=active.expires_at,
    )


def run_guarded(action: Callable[[], ChaosStatus]) -> ChaosStatus:
    try:
        return action()
    except ChaosFailure as failure:
        raise HTTPException(failure.status_code, failure.code) from failure


def build_chaos_router(controller: ServiceDownChaos, verifier: RequestVerifier) -> APIRouter:
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

    return router
