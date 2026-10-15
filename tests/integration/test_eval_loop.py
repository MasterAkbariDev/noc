import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from noc.db.models import EvalRun, Incident, ScenarioRun, Target
from noc.db.session import SessionFactory, transaction
from noc.detection.ingest import AlertIngestor
from noc.domain.variants import ModePolicy
from noc.evaluation.loop import (
    INTERRUPTED,
    NOT_DETECTED,
    PROVIDER_FAILED,
    WRONG_VARIANT,
    EvalLoop,
    LoopSettings,
)
from noc.evaluation.plan import EvalPlan
from noc.evaluation.store import DONE, INVALID, PENDING, RUNNING, materialize
from noc.policy.models import Environment
from noc.scenarios.definitions import ScenarioDefinition, parse_scenario
from noc.scenarios.runner import COMPLETED, TIMEOUT, PreconditionFailed, RunOutcome
from noc.store.targets import add_target
from tests.integration.test_alert_ingestion import StaticAlertSource
from tests.support.builders import KEY_ID, prometheus_alert

pytestmark = pytest.mark.integration

NOW = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
SCENARIO = parse_scenario(
    {
        "name": "service-down",
        "description": "stop demo-shop",
        "injection": {"type": "service_down", "resource_id": "svc:demo-shop", "ttl_seconds": 600},
        "detection_timeout_seconds": 240,
        "ground_truth": {
            "root_cause_code": "service_crashed",
            "resource_id": "svc:demo-shop",
            "acceptable_actions": ["restart_service"],
            "expected_outcome": "resolved",
        },
    }
)
PLAN = EvalPlan(
    name="pilot", scenarios=["service-down"], variants=["ma", "sa", "rb"], repetitions=1, seed=4
)


class FakeRunner:
    def __init__(self, sessions: SessionFactory) -> None:
        self.sessions = sessions
        self.script: list[str] = []
        self.modes_seen: list[str] = []
        self.count = 0

    async def run(
        self, scenario: ScenarioDefinition, target_name: str, resource_id: str | None = None
    ) -> RunOutcome:
        step = self.script.pop(0) if self.script else "resolve"
        if step == "busy":
            raise PreconditionFailed("target demo-1 has an active incident")
        async with transaction(self.sessions) as session:
            target = await session.scalar(select(Target).where(Target.name == target_name))
            assert target is not None
            run = ScenarioRun(
                scenario=scenario.name,
                target_id=target.id,
                resource_id="svc:demo-shop",
                status="running",
                ground_truth={},
                injected_at=NOW,
            )
            session.add(run)
        if step == "miss":
            return RunOutcome(run_id=run.id, status=TIMEOUT)
        self.count += 1
        async with transaction(self.sessions) as session:
            for old in await session.scalars(select(Incident)):
                old.status = "CLOSED"
        source = StaticAlertSource()
        source.alerts = [prometheus_alert(resource=f"svc:demo-shop-{self.count}")]
        await AlertIngestor(source, self.sessions, 2, ModePolicy("single", True)).poll_once()
        async with transaction(self.sessions) as session:
            incident = await session.scalar(select(Incident).where(Incident.status == "NEW"))
            assert incident is not None
            self.modes_seen.append(incident.mode)
            if step == "wrong":
                incident.mode = "single" if incident.mode != "single" else "multi"
            incident.status = "ESCALATED" if step in ("provider", "escalate") else "RESOLVED"
            if step == "provider":
                incident.escalation_reason = "llm_unavailable"
            return RunOutcome(run_id=run.id, status=COMPLETED, incident_id=incident.id)


async def prepare(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
        await materialize(session, PLAN)


def make_loop(sessions: SessionFactory, runner: FakeRunner, sleeps: list[float]) -> EvalLoop:
    async def sleep(seconds: float) -> None:
        sleeps.append(seconds)

    return EvalLoop(
        sessions,
        runner,
        {"service-down": SCENARIO},
        LoopSettings(
            target="demo-1", reset_seconds=60, provider_wait_seconds=900, max_waits_for_target=2
        ),
        lambda: NOW,
        sleep,
    )


async def runs(sessions: SessionFactory) -> list[EvalRun]:
    async with sessions() as session:
        return list(await session.scalars(select(EvalRun).order_by(EvalRun.position)))


async def override(sessions: SessionFactory) -> str | None:
    async with sessions() as session:
        return await session.scalar(select(Target.variant_override))


async def test_every_planned_run_executes_on_its_own_variant_in_schedule_order(
    sessions: SessionFactory,
) -> None:
    await prepare(sessions)
    runner = FakeRunner(sessions)
    summary = await make_loop(sessions, runner, []).run(PLAN.name)
    rows = await runs(sessions)
    assert summary.done == 3
    assert [row.status for row in rows] == [DONE, DONE, DONE]
    expected = {"ma": "multi", "sa": "single", "rb": "runbook"}
    assert runner.modes_seen == [expected[row.variant] for row in rows]
    assert all(row.scenario_run_id is not None for row in rows)
    assert await override(sessions) is None


async def test_a_wrong_variant_is_invalid_and_retried(sessions: SessionFactory) -> None:
    await prepare(sessions)
    runner = FakeRunner(sessions)
    runner.script = ["wrong"]
    summary = await make_loop(sessions, runner, []).run(PLAN.name, limit=1)
    rows = await runs(sessions)
    assert summary.requeued == 1
    assert rows[0].status == PENDING
    assert rows[0].error == WRONG_VARIANT
    assert rows[0].attempts == 1


async def test_a_run_gives_up_after_the_last_attempt(sessions: SessionFactory) -> None:
    await prepare(sessions)
    runner = FakeRunner(sessions)
    runner.script = ["miss", "miss", "miss"]
    await make_loop(sessions, runner, []).run(PLAN.name, limit=3)
    rows = await runs(sessions)
    assert rows[0].status == INVALID
    assert rows[0].attempts == 3
    assert rows[0].error == NOT_DETECTED


async def test_a_provider_failure_waits_longer_before_the_next_run(
    sessions: SessionFactory,
) -> None:
    await prepare(sessions)
    runner = FakeRunner(sessions)
    runner.script = ["provider"]
    sleeps: list[float] = []
    await make_loop(sessions, runner, sleeps).run(PLAN.name, limit=1)
    rows = await runs(sessions)
    assert rows[0].error == PROVIDER_FAILED
    assert sleeps[0] == 900


async def test_an_escalation_is_a_valid_result_not_an_error(sessions: SessionFactory) -> None:
    await prepare(sessions)
    runner = FakeRunner(sessions)
    runner.script = ["escalate"]
    summary = await make_loop(sessions, runner, []).run(PLAN.name, limit=1)
    assert summary.done == 1
    assert (await runs(sessions))[0].status == DONE


async def test_a_busy_target_puts_the_run_back_without_spending_an_attempt(
    sessions: SessionFactory,
) -> None:
    await prepare(sessions)
    runner = FakeRunner(sessions)
    runner.script = ["busy", "busy"]
    summary = await make_loop(sessions, runner, []).run(PLAN.name)
    rows = await runs(sessions)
    assert summary.stopped_reason is not None
    assert rows[0].status == PENDING
    assert rows[0].attempts == 0
    assert await override(sessions) is None


async def test_runs_left_running_by_a_crash_are_recovered(sessions: SessionFactory) -> None:
    await prepare(sessions)
    async with transaction(sessions) as session:
        row = await session.scalar(select(EvalRun).order_by(EvalRun.position).limit(1))
        assert row is not None
        row.status = RUNNING
        row.attempts = 1
        target = await session.scalar(select(Target))
        assert target is not None
        target.variant_override = "runbook"
    runner = FakeRunner(sessions)
    summary = await make_loop(sessions, runner, []).run(PLAN.name)
    assert "1 interrupted run(s) put back in the queue" in summary.messages
    rows = await runs(sessions)
    assert all(row.status == DONE for row in rows)
    first = rows[0]
    assert first.attempts == 2
    assert first.error is None
    assert first.error != INTERRUPTED
    assert await override(sessions) is None


async def test_unknown_scenarios_are_invalid_at_once(sessions: SessionFactory) -> None:
    async with transaction(sessions) as session:
        await add_target(
            session, "demo-1", "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
        await materialize(session, PLAN.model_copy(update={"scenarios": ["nope"], "name": "bad"}))
    summary = await make_loop(sessions, FakeRunner(sessions), []).run("bad")
    assert summary.invalid == 3
    rows = await runs(sessions)
    assert {row.status for row in rows} == {INVALID}
    assert uuid.UUID(str(rows[0].id))
