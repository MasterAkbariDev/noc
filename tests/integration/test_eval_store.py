from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from noc.db.models import EvalRun, ScenarioRun
from noc.db.session import SessionFactory, transaction
from noc.evaluation.plan import EvalPlan
from noc.evaluation.store import DONE, load_records, materialize, next_pending, status_counts
from noc.policy.models import Environment
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

PLAN = EvalPlan(
    name="pilot",
    scenarios=["service-down"],
    variants=["ma", "sa", "rb"],
    repetitions=2,
    seed=3,
)


async def test_materialize_is_idempotent(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        assert await materialize(session, PLAN) == 6
    async with transaction(sessions) as session:
        assert await materialize(session, PLAN) == 0
        assert await status_counts(session, PLAN.name) == {"pending": 6}


async def test_a_bigger_plan_only_adds_the_missing_runs(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await materialize(session, PLAN)
        bigger = PLAN.model_copy(update={"repetitions": 3})
        assert await materialize(session, bigger) == 3


async def test_next_pending_follows_the_schedule_and_filters_by_variant(
    sessions: SessionFactory,
) -> None:
    async with transaction(sessions) as session:
        await materialize(session, PLAN)
        everything = await next_pending(session, PLAN.name, None, 10)
        assert [run.position for run in everything] == sorted(run.position for run in everything)
        only_sa = await next_pending(session, PLAN.name, "sa", 10)
        assert {run.variant for run in only_sa} == {"sa"}
        assert len(only_sa) == 2


async def test_finished_runs_leave_the_pending_list_and_resume_continues(
    sessions: SessionFactory,
) -> None:
    async with transaction(sessions) as session:
        await materialize(session, PLAN)
        first = (await next_pending(session, PLAN.name, None, 1))[0]
        first.status = DONE
        first.finished_at = datetime.now(UTC)
    async with transaction(sessions) as session:
        remaining = await next_pending(session, PLAN.name, None, 10)
        assert len(remaining) == 5
        assert first.id not in {run.id for run in remaining}


async def test_records_join_the_scenario_run_and_the_expected_outcome(
    sessions: SessionFactory, tmp_path: Path
) -> None:
    async with transaction(sessions) as session:
        target = await add_target(
            session, "demo-1", "10.0.0.1", "https://10.0.0.1:8443", Environment.LAB, KEY_ID
        )
        run = ScenarioRun(
            scenario="service-down",
            target_id=target.id,
            resource_id="svc:demo-shop",
            status="completed",
            ground_truth={},
            injected_at=datetime.now(UTC),
            detection_seconds=12.0,
            root_cause_match=True,
            final_status="RESOLVED",
        )
        session.add(run)
        await session.flush()
        await materialize(session, PLAN)
        row = (await session.scalars(select(EvalRun).where(EvalRun.variant == "ma"))).first()
        assert row is not None
        row.status = DONE
        row.scenario_run_id = run.id
    async with sessions() as session:
        records = await load_records(session, PLAN.name, {"service-down": "resolved"})
    linked = [record for record in records if record.status == DONE]
    assert len(linked) == 1
    assert linked[0].root_cause_match is True
    assert linked[0].expected_outcome == "resolved"
    assert len(records) == 6
