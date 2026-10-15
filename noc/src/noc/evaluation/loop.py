import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Final, Literal, Protocol

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import EvalRun, Incident
from noc.db.session import SessionFactory, transaction
from noc.domain.incident_status import EscalationReason
from noc.domain.variants import variant_for_plan_name
from noc.evaluation.store import DONE, INVALID, PENDING, RUNNING
from noc.scenarios.definitions import ScenarioDefinition
from noc.scenarios.runner import COMPLETED, PreconditionFailed, RunOutcome
from noc.store.targets import set_variant_override

logger = structlog.get_logger(__name__)

ACTOR: Final = "eval-runner"
INTERRUPTED: Final = "interrupted: the runner stopped during this run"
NOT_DETECTED: Final = "the fault was not detected, so the variant was never exercised"
WRONG_VARIANT: Final = "the incident ran on a different variant than planned"
PROVIDER_FAILED: Final = "the model provider failed during the run"
UNKNOWN_SCENARIO: Final = "the plan names a scenario that is not defined"
NO_INCIDENT: Final = "no incident was linked to the run"


class Runner(Protocol):
    async def run(
        self, scenario: ScenarioDefinition, target_name: str, resource_id: str | None = None
    ) -> RunOutcome: ...


@dataclass(frozen=True)
class LoopSettings:
    target: str
    max_attempts: int = 3
    reset_seconds: float = 60.0
    provider_wait_seconds: float = 900.0
    max_waits_for_target: int = 10


@dataclass
class LoopSummary:
    done: int = 0
    invalid: int = 0
    requeued: int = 0
    stopped_reason: str | None = None
    messages: list[str] = field(default_factory=list)


ResultKind = Literal["done", "invalid", "requeued", "not_ready"]


@dataclass(frozen=True)
class RunResult:
    kind: ResultKind
    problem: str | None = None


@dataclass(frozen=True)
class Claimed:
    id: uuid.UUID
    scenario: str
    variant: str
    attempts: int


async def recover_interrupted(session: AsyncSession, plan: str, max_attempts: int) -> int:
    rows = list(
        await session.scalars(
            select(EvalRun).where(EvalRun.plan == plan, EvalRun.status == RUNNING)
        )
    )
    for row in rows:
        row.error = INTERRUPTED
        row.status = PENDING if row.attempts < max_attempts else INVALID
    await session.flush()
    return len(rows)


async def claim_next(session: AsyncSession, plan: str) -> Claimed | None:
    row = await session.scalar(
        select(EvalRun)
        .where(EvalRun.plan == plan, EvalRun.status == PENDING)
        .order_by(EvalRun.position)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if row is None:
        return None
    row.status = RUNNING
    row.attempts += 1
    await session.flush()
    return Claimed(row.id, row.scenario, row.variant, row.attempts)


async def release(session: AsyncSession, run_id: uuid.UUID) -> None:
    await session.execute(
        update(EvalRun)
        .where(EvalRun.id == run_id)
        .values(status=PENDING, attempts=EvalRun.attempts - 1)
    )


def verdict(outcome: RunOutcome, incident: Incident | None, planned: str) -> str | None:
    if outcome.incident_id is None:
        return NOT_DETECTED
    if incident is None:
        return NO_INCIDENT
    if incident.mode != planned:
        return WRONG_VARIANT
    if incident.escalation_reason == EscalationReason.LLM_UNAVAILABLE.value:
        return PROVIDER_FAILED
    return None


def count(summary: LoopSummary, result: RunResult) -> None:
    if result.kind == "done":
        summary.done += 1
    elif result.kind == "requeued":
        summary.requeued += 1
    else:
        summary.invalid += 1


class EvalLoop:
    def __init__(
        self,
        sessions: SessionFactory,
        runner: Runner,
        scenarios: dict[str, ScenarioDefinition],
        settings: LoopSettings,
        clock: Callable[[], datetime],
        sleep: Callable[[float], Awaitable[None]],
    ) -> None:
        self._sessions = sessions
        self._runner = runner
        self._scenarios = scenarios
        self._settings = settings
        self._clock = clock
        self._sleep = sleep

    async def run(self, plan: str, limit: int | None = None) -> LoopSummary:
        summary = LoopSummary()
        async with transaction(self._sessions) as session:
            recovered = await recover_interrupted(session, plan, self._settings.max_attempts)
            await set_variant_override(session, self._settings.target, None, ACTOR)
        if recovered:
            summary.messages.append(f"{recovered} interrupted run(s) put back in the queue")
        waits = 0
        while limit is None or summary.done + summary.invalid + summary.requeued < limit:
            async with transaction(self._sessions) as session:
                claimed = await claim_next(session, plan)
            if claimed is None:
                break
            result = await self._run_one(claimed)
            if result.kind == "not_ready":
                waits += 1
                if waits >= self._settings.max_waits_for_target:
                    summary.stopped_reason = (
                        "the target never became ready (an incident stayed open)"
                    )
                    break
                await self._sleep(self._settings.reset_seconds)
                continue
            waits = 0
            count(summary, result)
            pause = (
                self._settings.provider_wait_seconds
                if result.problem == PROVIDER_FAILED
                else self._settings.reset_seconds
            )
            await self._sleep(pause)
        return summary

    async def _run_one(self, claimed: Claimed) -> RunResult:
        scenario = self._scenarios.get(claimed.scenario)
        if scenario is None:
            await self._finish(claimed, None, UNKNOWN_SCENARIO, final=True)
            return RunResult("invalid", UNKNOWN_SCENARIO)
        variant = variant_for_plan_name(claimed.variant)
        async with transaction(self._sessions) as session:
            await set_variant_override(session, self._settings.target, variant, ACTOR)
        try:
            outcome = await self._runner.run(scenario, self._settings.target)
        except PreconditionFailed as error:
            logger.info("eval_target_not_ready", run=str(claimed.id), reason=str(error))
            async with transaction(self._sessions) as session:
                await release(session, claimed.id)
            return RunResult("not_ready")
        finally:
            async with transaction(self._sessions) as session:
                await set_variant_override(session, self._settings.target, None, ACTOR)
        problem = await self._judge(outcome, variant)
        if problem is None:
            await self._finish(claimed, outcome, None, final=True)
            return RunResult("done")
        final = claimed.attempts >= self._settings.max_attempts
        await self._finish(claimed, outcome, problem, final=final)
        return RunResult("invalid" if final else "requeued", problem)

    async def _judge(self, outcome: RunOutcome, variant: str) -> str | None:
        incident = None
        if outcome.incident_id is not None:
            async with self._sessions() as session:
                incident = await session.get(Incident, outcome.incident_id)
        problem = verdict(outcome, incident, variant)
        if problem is None and outcome.status != COMPLETED:
            logger.info("eval_run_outcome_timeout", run=str(outcome.run_id))
        return problem

    async def _finish(
        self, claimed: Claimed, outcome: RunOutcome | None, problem: str | None, final: bool
    ) -> None:
        async with transaction(self._sessions) as session:
            row = await session.get_one(EvalRun, claimed.id)
            row.scenario_run_id = outcome.run_id if outcome is not None else None
            row.error = problem
            if problem is None:
                row.status = DONE
                row.finished_at = self._clock()
            elif final:
                row.status = INVALID
                row.finished_at = self._clock()
            else:
                row.status = PENDING
