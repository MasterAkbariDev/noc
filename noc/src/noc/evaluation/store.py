from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from noc.db.models import EvalRun, ScenarioRun
from noc.evaluation.plan import EvalPlan, build_schedule

PENDING = "pending"
RUNNING = "running"
DONE = "done"
INVALID = "invalid"


@dataclass(frozen=True)
class RunRecord:
    scenario: str
    variant: str
    repetition: int
    seed: int
    status: str
    attempts: int
    detected: bool | None
    root_cause_match: bool | None
    detection_seconds: float | None
    final_status: str | None
    expected_outcome: str | None


async def materialize(session: AsyncSession, plan: EvalPlan) -> int:
    values = [
        {
            "plan": plan.name,
            "scenario": run.scenario,
            "variant": run.variant,
            "repetition": run.repetition,
            "seed": run.seed,
            "position": run.position,
            "status": PENDING,
            "attempts": 0,
        }
        for run in build_schedule(plan)
    ]
    statement = (
        insert(EvalRun)
        .values(values)
        .on_conflict_do_nothing(constraint="uq_eval_runs_cell")
        .returning(EvalRun.id)
    )
    inserted = await session.scalars(statement)
    return len(inserted.all())


async def status_counts(session: AsyncSession, plan_name: str) -> dict[str, int]:
    rows = await session.execute(
        select(EvalRun.status, func.count())
        .where(EvalRun.plan == plan_name)
        .group_by(EvalRun.status)
    )
    return {status: count for status, count in rows.all()}


async def next_pending(
    session: AsyncSession, plan_name: str, variant: str | None, limit: int
) -> list[EvalRun]:
    query = (
        select(EvalRun)
        .where(EvalRun.plan == plan_name, EvalRun.status == PENDING)
        .order_by(EvalRun.position)
        .limit(limit)
    )
    if variant is not None:
        query = query.where(EvalRun.variant == variant)
    return list(await session.scalars(query))


async def load_records(
    session: AsyncSession, plan_name: str, expected: Mapping[str, str]
) -> list[RunRecord]:
    rows = await session.execute(
        select(EvalRun, ScenarioRun)
        .outerjoin(ScenarioRun, EvalRun.scenario_run_id == ScenarioRun.id)
        .where(EvalRun.plan == plan_name)
        .order_by(EvalRun.position)
    )
    return [
        RunRecord(
            scenario=run.scenario,
            variant=run.variant,
            repetition=run.repetition,
            seed=run.seed,
            status=run.status,
            attempts=run.attempts,
            detected=None if scenario is None else scenario.incident_id is not None,
            root_cause_match=None if scenario is None else scenario.root_cause_match,
            detection_seconds=None if scenario is None else scenario.detection_seconds,
            final_status=None if scenario is None else scenario.final_status,
            expected_outcome=expected.get(run.scenario),
        )
        for run, scenario in rows.all()
    ]
