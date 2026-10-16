import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Annotated, Protocol, TypeGuard
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse

from noc_sentinel.action_store import ActionStore, StoredAction
from noc_sentinel.config import SentinelConfig
from noc_sentinel.halt import is_halted
from noc_sentinel.host_actions import (
    HOST_ACTIONS,
    UNIT_KINDS,
    host_action_timeout,
    host_action_unit,
    is_host_action,
)
from noc_sentinel.security import RequestVerifier
from noc_sentinel.tools.systemd import SystemctlRunner, read_service_status
from noc_shared.actions import (
    ActionRequest,
    ActionResult,
    ActionType,
    ServiceActionType,
    compute_action_hash,
)
from noc_shared.resources import ManagedResource, ResourceKind
from noc_shared.signing import VerifiedRequest
from noc_shared.tools import ServiceStatus

SYSTEMCTL_PATH = "/usr/bin/systemctl"
ACTION_TIMEOUT_SECONDS = 30
WAIT_FOR_ACTIVE_SECONDS = 10
POLL_INTERVAL_SECONDS = 1
RATE_WINDOW = timedelta(hours=1)
ACTION_VERBS: dict[ServiceActionType, str] = {
    "start_service": "start",
    "restart_service": "restart",
}
STOPPED_STATES = frozenset({"inactive", "failed"})
PROTECTED_UNITS = frozenset(
    {
        "ssh.service",
        "sshd.service",
        "noc-sentinel.service",
        "systemd-journald.service",
        "dbus.service",
        "networking.service",
        "systemd-networkd.service",
        "docker.service",
    }
)
PROTECTED_UNIT_PREFIX = "systemd-"
AUDIT_LOGGER = logging.getLogger("noc-sentinel-audit")


class ActionRunner(Protocol):
    def run(self, argv: tuple[str, ...], timeout_seconds: int) -> int: ...


class SubprocessActionRunner:
    def run(self, argv: tuple[str, ...], timeout_seconds: int) -> int:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            check=False,
        )
        return completed.returncode


class ActionRefused(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(code)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class ActionOutcome:
    status_code: int
    result: ActionResult


def is_service_action(value: str) -> TypeGuard[ServiceActionType]:
    return value in ACTION_VERBS


def is_action_type(value: str) -> TypeGuard[ActionType]:
    return is_service_action(value) or is_host_action(value)


def mutation_argv(action_type: ActionType, resource: ManagedResource) -> tuple[str, ...] | None:
    if is_service_action(action_type):
        return (SYSTEMCTL_PATH, ACTION_VERBS[action_type], resource.name)
    if is_host_action(action_type):
        unit = host_action_unit(action_type, resource)
        return None if unit is None else (SYSTEMCTL_PATH, "start", unit)
    return None


def action_timeout(action_type: ActionType) -> int:
    return (
        host_action_timeout(action_type) if is_host_action(action_type) else ACTION_TIMEOUT_SECONDS
    )


def allowed_kinds(action_type: ActionType) -> frozenset[ResourceKind]:
    if is_host_action(action_type):
        return HOST_ACTIONS[action_type].kinds
    return frozenset({ResourceKind.SYSTEMD_UNIT})


def refused_result(
    action_type: ActionType, request: ActionRequest, refusal: ActionRefused, now: datetime
) -> ActionResult:
    return ActionResult(
        action_id=request.action_id,
        action_type=action_type,
        resource_id=request.resource_id,
        status="refused",
        code=refusal.code,
        message=refusal.message,
        started_at=now,
        finished_at=now,
        before=None,
        after=None,
    )


def log_execution(result: ActionResult, request: ActionRequest) -> None:
    AUDIT_LOGGER.info(
        "action_id=%s type=%s resource=%s status=%s code=%s approval_id=%s auto_policy_ref=%s",
        result.action_id,
        result.action_type,
        result.resource_id,
        result.status,
        result.code,
        request.approval_id,
        request.auto_policy_ref,
    )


class ActionExecutor:
    def __init__(
        self,
        config: SentinelConfig,
        systemctl: SystemctlRunner,
        runner: ActionRunner,
        store: ActionStore,
        clock: Callable[[], datetime],
        sleep: Callable[[float], None],
    ) -> None:
        self._config = config
        self._systemctl = systemctl
        self._runner = runner
        self._store = store
        self._clock = clock
        self._sleep = sleep
        self._lock = threading.Lock()

    def lookup(self, action_id: UUID) -> ActionResult | None:
        stored = self._store.get(action_id)
        return None if stored is None else stored.result

    def execute(self, action_type: ActionType, request: ActionRequest) -> ActionOutcome:
        started_at = self._clock()
        with self._lock:
            try:
                return self._execute_checked(action_type, request, started_at)
            except ActionRefused as refusal:
                return ActionOutcome(
                    refusal.status_code,
                    refused_result(action_type, request, refusal, started_at),
                )

    def _execute_checked(
        self, action_type: ActionType, request: ActionRequest, started_at: datetime
    ) -> ActionOutcome:
        self._check_not_halted()
        self._check_hash(action_type, request)
        stored = self._store.get(request.action_id)
        if stored is not None:
            return self._deduplicate(stored, request)
        resource = self._authorized_resource(action_type, request.resource_id)
        if resource.kind in UNIT_KINDS:
            self._check_not_protected(resource.name)
        self._check_rate(resource, started_at)
        return self._run_action(action_type, request, resource, started_at)

    def _check_not_halted(self) -> None:
        if is_halted(self._config.halt_file):
            raise ActionRefused(409, "HALTED", "sentinel is halted by the HALT file")

    def _check_hash(self, action_type: ActionType, request: ActionRequest) -> None:
        expected = compute_action_hash(
            action_type,
            self._config.target,
            request.resource_id,
            request.params,
            request.incident_id,
            request.attempt,
        )
        if expected != request.action_hash:
            raise ActionRefused(422, "HASH_MISMATCH", "action_hash does not match the request")

    def _deduplicate(self, stored: StoredAction, request: ActionRequest) -> ActionOutcome:
        if stored.action_hash != request.action_hash:
            raise ActionRefused(409, "ACTION_ID_REUSED", "action_id belongs to another action")
        return ActionOutcome(200, stored.result.model_copy(update={"deduplicated": True}))

    def _authorized_resource(self, action_type: ActionType, resource_id: str) -> ManagedResource:
        resource = self._config.resource(resource_id)
        if (
            resource is None
            or resource.kind not in allowed_kinds(action_type)
            or action_type not in resource.allowed_actions
        ):
            raise ActionRefused(403, "NOT_ALLOWED", "action is not allowed on this resource")
        if mutation_argv(action_type, resource) is None:
            raise ActionRefused(403, "BAD_RESOURCE_NAME", "resource name cannot be passed safely")
        return resource

    def _check_not_protected(self, unit: str) -> None:
        if unit in PROTECTED_UNITS or unit.startswith(PROTECTED_UNIT_PREFIX):
            raise ActionRefused(403, "PROTECTED", "unit is protected from actions")

    def _check_rate(self, resource: ManagedResource, now: datetime) -> None:
        recent = self._store.count_since(resource.id, now - RATE_WINDOW)
        if recent >= self._config.actions.max_per_resource_per_hour:
            raise ActionRefused(429, "RATE_LIMITED", "too many actions on this resource this hour")

    def _run_action(
        self,
        action_type: ActionType,
        request: ActionRequest,
        resource: ManagedResource,
        started_at: datetime,
    ) -> ActionOutcome:
        executing = ActionResult(
            action_id=request.action_id,
            action_type=action_type,
            resource_id=resource.id,
            status="executing",
            code=None,
            message="action started",
            started_at=started_at,
            finished_at=None,
            before=None,
            after=None,
        )
        self._store.insert_executing(request.action_hash, executing)
        try:
            before = self._unit_status(resource)
        except (subprocess.SubprocessError, OSError):
            return self._finish_unreadable(executing, request)
        argv = mutation_argv(action_type, resource)
        failure = (
            ("INTERNAL", "no command for this action")
            if argv is None
            else self._mutate(argv, action_timeout(action_type))
        )
        after, failure = self._check_after(action_type, resource, failure)
        result = ActionResult(
            action_id=request.action_id,
            action_type=action_type,
            resource_id=resource.id,
            status="failed" if failure is not None else "succeeded",
            code=None if failure is None else failure[0],
            message=success_message(action_type) if failure is None else failure[1],
            started_at=started_at,
            finished_at=self._clock(),
            before=before,
            after=after,
        )
        self._store.finish(result)
        log_execution(result, request)
        return ActionOutcome(200, result)

    def _finish_unreadable(self, executing: ActionResult, request: ActionRequest) -> ActionOutcome:
        result = executing.model_copy(
            update={
                "status": "failed",
                "code": "STATUS_UNREADABLE",
                "message": "unit state could not be read, nothing was changed",
                "finished_at": self._clock(),
            }
        )
        self._store.finish(result)
        log_execution(result, request)
        return ActionOutcome(200, result)

    def _unit_status(self, resource: ManagedResource) -> ServiceStatus | None:
        if resource.kind not in UNIT_KINDS:
            return None
        return read_service_status(resource, self._systemctl)

    def _check_after(
        self,
        action_type: ActionType,
        resource: ManagedResource,
        failure: tuple[str, str] | None,
    ) -> tuple[ServiceStatus | None, tuple[str, str] | None]:
        if failure is None and is_service_action(action_type):
            active = self._wait_until_active(resource)
            if active.active_state != "active":
                failure = (
                    "NOT_ACTIVE",
                    f"unit did not reach active within {WAIT_FOR_ACTIVE_SECONDS} s",
                )
            return active, failure
        after = self._unit_status(resource)
        if (
            failure is None
            and action_type == "stop_service"
            and after is not None
            and after.active_state not in STOPPED_STATES
        ):
            failure = ("STILL_RUNNING", f"unit is {after.active_state} after the stop")
        return after, failure

    def _mutate(self, argv: tuple[str, ...], timeout_seconds: int) -> tuple[str, str] | None:
        try:
            returncode = self._runner.run(argv, timeout_seconds)
        except subprocess.TimeoutExpired:
            return ("TIMEOUT", f"systemctl did not finish within {timeout_seconds} s")
        except OSError:
            return ("INTERNAL", "systemctl could not be executed")
        if returncode != 0:
            return (f"EXIT_{returncode}", f"systemctl exited with status {returncode}")
        return None

    def _wait_until_active(self, resource: ManagedResource) -> ServiceStatus:
        status = read_service_status(resource, self._systemctl)
        for _ in range(WAIT_FOR_ACTIVE_SECONDS // POLL_INTERVAL_SECONDS):
            if status.active_state == "active":
                return status
            self._sleep(POLL_INTERVAL_SECONDS)
            status = read_service_status(resource, self._systemctl)
        return status


def success_message(action_type: ActionType) -> str:
    if is_service_action(action_type):
        return "unit is active"
    if action_type == "stop_service":
        return "unit is stopped"
    return "host action finished"


def build_actions_router(executor: ActionExecutor, verifier: RequestVerifier) -> APIRouter:
    router = APIRouter()
    Signed = Annotated[VerifiedRequest, Depends(verifier)]

    @router.post("/v1/actions/{action_type}")
    def run_action(action_type: str, request: ActionRequest, _: Signed) -> JSONResponse:
        if not is_action_type(action_type):
            raise HTTPException(404, "NOT_FOUND")
        outcome = executor.execute(action_type, request)
        return JSONResponse(outcome.result.model_dump(mode="json"), status_code=outcome.status_code)

    @router.get("/v1/actions/{action_id}")
    def get_action(action_id: UUID, _: Signed) -> ActionResult:
        result = executor.lookup(action_id)
        if result is None:
            raise HTTPException(404, "NOT_FOUND")
        return result

    return router
