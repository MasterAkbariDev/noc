import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Final

import structlog
from sqlalchemy import func, select

from noc.audit.chain import append_audit
from noc.db.base import new_id
from noc.db.models import ACTIVE_INCIDENT_PREDICATE, Incident, ScenarioRun
from noc.db.session import SessionFactory, transaction
from noc.domain.incident_status import IncidentStatus
from noc.scenarios.chaos_client import NOT_ACTIVE, ChaosClient, ChaosError
from noc.scenarios.definitions import (
    AppFaultInjection,
    CpuBurnInjection,
    DiskFillInjection,
    Injection,
    InjectionType,
    ScenarioDefinition,
    ServiceDownInjection,
)
from noc.store.targets import find_target

logger = structlog.get_logger(__name__)

ACTOR: Final = "scenario-runner"
DEFAULT_POLL_SECONDS: Final = 5.0

RUNNING: Final = "running"
COMPLETED: Final = "completed"
TIMEOUT: Final = "timeout"
FAILED: Final = "failed"

TERMINAL_STATUSES: Final = frozenset(
    {
        IncidentStatus.ESCALATED.value,
        IncidentStatus.RESOLVED.value,
        IncidentStatus.SELF_RESOLVED.value,
        IncidentStatus.CLOSED.value,
    }
)


class PreconditionFailed(Exception):
    pass


@dataclass(frozen=True)
class IncidentSnapshot:
    incident_id: uuid.UUID
    status: str
    root_cause_code: str | None
    opened_at: datetime


@dataclass(frozen=True)
class RunOutcome:
    run_id: uuid.UUID
    status: str
    incident_id: uuid.UUID | None = None
    detected_at: datetime | None = None
    detection_seconds: float | None = None
    final_status: str | None = None
    root_cause_match: bool | None = None


def snapshot_of(incident: Incident) -> IncidentSnapshot:
    return IncidentSnapshot(
        incident_id=incident.id,
        status=incident.status,
        root_cause_code=incident.root_cause_code,
        opened_at=incident.opened_at,
    )


def run_resource(injection: Injection, target_name: str, resource_id: str | None) -> str:
    match injection:
        case ServiceDownInjection() | AppFaultInjection():
            return resource_id or injection.resource_id
        case CpuBurnInjection() | DiskFillInjection():
            return f"host:{target_name}"


class ScenarioRunner:
    def __init__(
        self,
        sessions: SessionFactory,
        chaos: ChaosClient,
        clock: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]],
        poll_seconds: float = DEFAULT_POLL_SECONDS,
    ) -> None:
        self._sessions = sessions
        self._chaos = chaos
        self._clock = clock
        self._sleep = sleep
        self._poll_seconds = poll_seconds

    async def run(
        self, scenario: ScenarioDefinition, target_name: str, resource_id: str | None = None
    ) -> RunOutcome:
        injection = scenario.injection
        resource = run_resource(injection, target_name, resource_id)
        target_id = await self._check_preconditions(target_name, resource)
        injected_at = self._clock()
        run_id = await self._start_run(scenario, target_name, target_id, resource, injected_at)
        try:
            await self._start_chaos(injection, resource)
            outcome = await self._observe(run_id, scenario, target_id, injected_at)
        except BaseException as error:
            await self._stop_after_failure(injection.type, resource)
            if isinstance(error, Exception):
                await self._store(RunOutcome(run_id=run_id, status=FAILED), scenario, str(error))
            raise
        await self.stop_injection(injection.type, resource)
        await self._store(outcome, scenario, None)
        return outcome

    async def _start_chaos(self, injection: Injection, resource_id: str) -> None:
        match injection:
            case ServiceDownInjection():
                await self._chaos.start_service_down(resource_id, injection.ttl_seconds)
            case CpuBurnInjection():
                await self._chaos.start_cpu_burn(injection.workers, injection.ttl_seconds)
            case DiskFillInjection():
                await self._chaos.start_disk_fill(injection.target_percent, injection.ttl_seconds)
            case AppFaultInjection():
                await self._chaos.start_app_fault(
                    resource_id, injection.fault, injection.ttl_seconds
                )

    async def _stop_after_failure(self, kind: InjectionType, resource_id: str) -> None:
        try:
            await self.stop_injection(kind, resource_id)
        except Exception:
            logger.exception("chaos_stop_failed_after_error", resource_id=resource_id)

    async def stop_injection(self, kind: InjectionType, resource_id: str) -> bool:
        try:
            await self._stop_chaos(kind, resource_id)
        except ChaosError as error:
            if error.code == NOT_ACTIVE:
                return False
            raise
        return True

    async def _stop_chaos(self, kind: InjectionType, resource_id: str) -> None:
        match kind:
            case "service_down":
                await self._chaos.stop_service_down(resource_id)
            case "cpu_burn":
                await self._chaos.stop_cpu_burn()
            case "disk_fill":
                await self._chaos.stop_disk_fill()
            case "app_fault":
                await self._chaos.stop_app_fault(resource_id)

    async def _check_preconditions(self, target_name: str, resource_id: str) -> uuid.UUID:
        async with self._sessions() as session:
            target = await find_target(session, target_name)
            if target is None:
                raise PreconditionFailed(f"unknown target {target_name}")
            open_incidents = await session.scalar(
                select(func.count())
                .select_from(Incident)
                .where(Incident.target_id == target.id, ACTIVE_INCIDENT_PREDICATE)
            )
            target_id = target.id
        if open_incidents:
            raise PreconditionFailed(f"target {target_name} has an active incident")
        state = await self._chaos.status()
        if state.active:
            raise PreconditionFailed(f"chaos already active on {state.resource_id}")
        return target_id

    async def _start_run(
        self,
        scenario: ScenarioDefinition,
        target_name: str,
        target_id: uuid.UUID,
        resource_id: str,
        injected_at: datetime,
    ) -> uuid.UUID:
        run = ScenarioRun(
            id=new_id(),
            scenario=scenario.name,
            target_id=target_id,
            resource_id=resource_id,
            status=RUNNING,
            ground_truth=scenario.ground_truth.model_dump(mode="json"),
            injected_at=injected_at,
        )
        async with transaction(self._sessions) as session:
            session.add(run)
            await append_audit(
                session,
                ACTOR,
                "scenario_run_started",
                scenario.name,
                {"target": target_name, "resource_id": resource_id},
            )
        return run.id

    async def _observe(
        self,
        run_id: uuid.UUID,
        scenario: ScenarioDefinition,
        target_id: uuid.UUID,
        injected_at: datetime,
    ) -> RunOutcome:
        detection_deadline = injected_at + timedelta(seconds=scenario.detection_timeout_seconds)
        detected = await self._poll_until(
            lambda: self._first_incident_since(target_id, injected_at), detection_deadline
        )
        if detected is None:
            return RunOutcome(run_id=run_id, status=TIMEOUT)
        outcome_deadline = self._clock() + timedelta(seconds=scenario.outcome_timeout_seconds)
        reached = await self._poll_until(
            lambda: self._terminal_incident(detected.incident_id), outcome_deadline
        )
        final = await self._load_incident(detected.incident_id)
        return RunOutcome(
            run_id=run_id,
            status=COMPLETED if reached is not None else TIMEOUT,
            incident_id=final.incident_id,
            detected_at=detected.opened_at,
            detection_seconds=(detected.opened_at - injected_at).total_seconds(),
            final_status=final.status,
            root_cause_match=final.root_cause_code == scenario.ground_truth.root_cause_code,
        )

    async def _poll_until[T](
        self, probe: Callable[[], Awaitable[T | None]], deadline: datetime
    ) -> T | None:
        while True:
            found = await probe()
            if found is not None:
                return found
            remaining = (deadline - self._clock()).total_seconds()
            if remaining <= 0:
                return None
            await self._sleep(min(self._poll_seconds, remaining))

    async def _first_incident_since(
        self, target_id: uuid.UUID, since: datetime
    ) -> IncidentSnapshot | None:
        async with self._sessions() as session:
            incident = await session.scalar(
                select(Incident)
                .where(Incident.target_id == target_id, Incident.opened_at >= since)
                .order_by(Incident.opened_at)
                .limit(1)
            )
            return snapshot_of(incident) if incident is not None else None

    async def _terminal_incident(self, incident_id: uuid.UUID) -> IncidentSnapshot | None:
        async with self._sessions() as session:
            incident = await session.scalar(
                select(Incident).where(
                    Incident.id == incident_id, Incident.status.in_(sorted(TERMINAL_STATUSES))
                )
            )
            return snapshot_of(incident) if incident is not None else None

    async def _load_incident(self, incident_id: uuid.UUID) -> IncidentSnapshot:
        async with self._sessions() as session:
            incident = await session.get(Incident, incident_id)
            if incident is None:
                raise LookupError(f"incident {incident_id} disappeared")
            return snapshot_of(incident)

    async def _store(
        self, outcome: RunOutcome, scenario: ScenarioDefinition, error: str | None
    ) -> None:
        async with transaction(self._sessions) as session:
            row = await session.get_one(ScenarioRun, outcome.run_id)
            row.status = outcome.status
            row.incident_id = outcome.incident_id
            row.detected_at = outcome.detected_at
            row.detection_seconds = outcome.detection_seconds
            row.final_status = outcome.final_status
            row.root_cause_match = outcome.root_cause_match
            row.error = error
            row.finished_at = self._clock()
            await append_audit(
                session,
                ACTOR,
                "scenario_run_finished",
                scenario.name,
                {
                    "run_id": str(outcome.run_id),
                    "status": outcome.status,
                    "final_status": outcome.final_status,
                    "root_cause_match": outcome.root_cause_match,
                },
            )
