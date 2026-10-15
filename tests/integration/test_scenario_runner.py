import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import select

from noc.db.models import Incident, ScenarioRun
from noc.db.session import SessionFactory, transaction
from noc.policy.models import Environment
from noc.scenarios.chaos_client import ChaosError, ChaosState
from noc.scenarios.definitions import AppFault, ScenarioDefinition, load_scenario
from noc.scenarios.runner import PreconditionFailed, ScenarioRunner
from noc.store.targets import add_target
from tests.support.builders import KEY_ID

pytestmark = pytest.mark.integration

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"
START = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
TARGET = "demo-1"
RESOURCE = "svc:demo-shop"

ScriptAction = Callable[[datetime], Awaitable[None]]


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.current = start
        self.on_sleep: Callable[[datetime], Awaitable[None]] | None = None

    def now(self) -> datetime:
        return self.current

    async def sleep(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)
        if self.on_sleep is not None:
            await self.on_sleep(self.current)


class FakeChaos:
    def __init__(self) -> None:
        self.active = False
        self.fail_start = False
        self.fail_stop = False
        self.starts: list[tuple[str, int]] = []
        self.stops: list[str] = []
        self.events: list[str] = []

    async def status(self) -> ChaosState:
        return ChaosState(active=self.active)

    async def start_service_down(self, resource_id: str, ttl_seconds: int) -> ChaosState:
        self.events.append("start:service_down")
        self._check_start()
        self.starts.append((resource_id, ttl_seconds))
        return self._activate(resource_id)

    async def stop_service_down(self, resource_id: str) -> ChaosState:
        self.stops.append(resource_id)
        self.events.append("stop:service_down")
        return self._deactivate()

    async def start_cpu_burn(self, workers: int, ttl_seconds: int) -> ChaosState:
        self.events.append("start:cpu_burn")
        self._check_start()
        return self._activate("host:demo-1")

    async def stop_cpu_burn(self) -> ChaosState:
        self.events.append("stop:cpu_burn")
        return self._deactivate()

    async def start_disk_fill(self, target_percent: int, ttl_seconds: int) -> ChaosState:
        self.events.append("start:disk_fill")
        self._check_start()
        return self._activate("host:demo-1")

    async def stop_disk_fill(self) -> ChaosState:
        self.events.append("stop:disk_fill")
        return self._deactivate()

    async def start_app_fault(
        self, resource_id: str, fault: AppFault, ttl_seconds: int
    ) -> ChaosState:
        self.events.append(f"start:app_fault:{fault}")
        self._check_start()
        self.starts.append((resource_id, ttl_seconds))
        return self._activate(resource_id)

    async def stop_app_fault(self, resource_id: str) -> ChaosState:
        self.stops.append(resource_id)
        self.events.append("stop:app_fault")
        return self._deactivate()

    def _check_start(self) -> None:
        if self.fail_start:
            raise ChaosError("INTERNAL")

    def _activate(self, resource_id: str) -> ChaosState:
        self.active = True
        return ChaosState(active=True, resource_id=resource_id)

    def _deactivate(self) -> ChaosState:
        if self.fail_stop:
            raise ChaosError("INTERNAL")
        if not self.active:
            raise ChaosError("NOT_ACTIVE")
        self.active = False
        return ChaosState(active=False)


class Script:
    def __init__(self, clock: FakeClock) -> None:
        self._start = clock.now()
        self._steps: list[tuple[float, ScriptAction]] = []
        clock.on_sleep = self._tick

    def at(self, seconds: float, action: ScriptAction) -> None:
        self._steps.append((seconds, action))
        self._steps.sort(key=lambda step: step[0])

    async def _tick(self, now: datetime) -> None:
        while self._steps and now >= self._start + timedelta(seconds=self._steps[0][0]):
            _, action = self._steps.pop(0)
            await action(now)


def detects(
    sessions: SessionFactory, target_id: uuid.UUID, store: dict[str, uuid.UUID]
) -> ScriptAction:
    async def action(now: datetime) -> None:
        async with transaction(sessions) as session:
            incident = Incident(
                target_id=target_id,
                status="INVESTIGATING",
                severity="critical",
                title="demo-shop is down",
                trace_id="0" * 32,
                opened_at=now,
            )
            session.add(incident)
        store["incident"] = incident.id

    return action


def moves_to(
    sessions: SessionFactory, store: dict[str, uuid.UUID], status: str, root_cause: str | None
) -> ScriptAction:
    async def action(now: datetime) -> None:
        async with transaction(sessions) as session:
            incident = await session.get_one(Incident, store["incident"])
            incident.status = status
            incident.root_cause_code = root_cause

    return action


def raises(message: str) -> ScriptAction:
    async def action(now: datetime) -> None:
        raise RuntimeError(message)

    return action


async def insert_open_incident(sessions: SessionFactory, target_id: uuid.UUID) -> None:
    async with transaction(sessions) as session:
        session.add(
            Incident(
                target_id=target_id,
                status="INVESTIGATING",
                severity="critical",
                title="already open",
                trace_id="1" * 32,
                opened_at=START,
            )
        )


@pytest.fixture
async def target_id(sessions: SessionFactory) -> uuid.UUID:
    async with transaction(sessions) as session:
        target = await add_target(
            session, TARGET, "10.0.0.2", "https://demo-1:9443", Environment.LAB, KEY_ID
        )
    return target.id


@pytest.fixture
def scenario() -> ScenarioDefinition:
    return load_scenario(SCENARIOS_DIR / "service-down.yaml")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(START)


@pytest.fixture
def chaos() -> FakeChaos:
    return FakeChaos()


@pytest.fixture
def runner(sessions: SessionFactory, chaos: FakeChaos, clock: FakeClock) -> ScenarioRunner:
    return ScenarioRunner(sessions, chaos, clock.now, clock.sleep, poll_seconds=5.0)


async def load_runs(sessions: SessionFactory) -> list[ScenarioRun]:
    async with sessions() as session:
        return list((await session.scalars(select(ScenarioRun))).all())


async def test_success_path_records_detection_and_root_cause_match(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    clock: FakeClock,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    store: dict[str, uuid.UUID] = {}
    script = Script(clock)
    script.at(30, detects(sessions, target_id, store))
    script.at(90, moves_to(sessions, store, "ESCALATED", "service_crashed"))

    outcome = await runner.run(scenario, TARGET, RESOURCE)

    assert outcome.status == "completed"
    assert outcome.incident_id == store["incident"]
    assert outcome.detection_seconds == 30.0
    assert outcome.final_status == "ESCALATED"
    assert outcome.root_cause_match is True
    assert chaos.starts == [(RESOURCE, 600)]
    assert chaos.stops == [RESOURCE]
    assert chaos.active is False
    [run] = await load_runs(sessions)
    assert run.status == "completed"
    assert run.scenario == "service-down"
    assert run.ground_truth["root_cause_code"] == "service_crashed"
    assert run.finished_at is not None


async def test_detection_timeout_still_stops_chaos(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    outcome = await runner.run(scenario, TARGET, RESOURCE)

    assert outcome.status == "timeout"
    assert outcome.incident_id is None
    assert outcome.detection_seconds is None
    assert chaos.stops == [RESOURCE]
    assert chaos.active is False
    [run] = await load_runs(sessions)
    assert run.status == "timeout"


async def test_outcome_timeout_keeps_detection_and_stops_chaos(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    clock: FakeClock,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    store: dict[str, uuid.UUID] = {}
    script = Script(clock)
    script.at(10, detects(sessions, target_id, store))

    outcome = await runner.run(scenario, TARGET, RESOURCE)

    assert outcome.status == "timeout"
    assert outcome.incident_id == store["incident"]
    assert outcome.detection_seconds == 10.0
    assert outcome.final_status == "INVESTIGATING"
    assert chaos.stops == [RESOURCE]
    assert chaos.active is False


async def test_open_incident_blocks_injection(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    await insert_open_incident(sessions, target_id)

    with pytest.raises(PreconditionFailed, match="active incident"):
        await runner.run(scenario, TARGET, RESOURCE)

    assert chaos.starts == []
    assert chaos.stops == []
    assert await load_runs(sessions) == []


async def test_active_chaos_blocks_injection(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    chaos.active = True

    with pytest.raises(PreconditionFailed, match="already active"):
        await runner.run(scenario, TARGET, RESOURCE)

    assert chaos.starts == []
    assert await load_runs(sessions) == []


async def test_unknown_target_is_a_precondition_failure(
    runner: ScenarioRunner, scenario: ScenarioDefinition, chaos: FakeChaos
) -> None:
    with pytest.raises(PreconditionFailed, match="unknown target"):
        await runner.run(scenario, "no-such-host", RESOURCE)

    assert chaos.starts == []


async def test_chaos_is_stopped_when_a_step_raises_mid_run(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    clock: FakeClock,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    store: dict[str, uuid.UUID] = {}
    script = Script(clock)
    script.at(30, detects(sessions, target_id, store))
    script.at(60, raises("database went away"))

    with pytest.raises(RuntimeError, match="database went away"):
        await runner.run(scenario, TARGET, RESOURCE)

    assert chaos.stops == [RESOURCE]
    assert chaos.active is False
    [run] = await load_runs(sessions)
    assert run.status == "failed"
    assert run.error == "database went away"


async def test_failed_start_still_attempts_stop_and_ignores_not_active(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    chaos.fail_start = True

    with pytest.raises(ChaosError, match="INTERNAL"):
        await runner.run(scenario, TARGET, RESOURCE)

    assert chaos.stops == [RESOURCE]
    [run] = await load_runs(sessions)
    assert run.status == "failed"
    assert run.error == "INTERNAL"


async def test_original_error_survives_a_failing_stop(
    runner: ScenarioRunner,
    scenario: ScenarioDefinition,
    clock: FakeClock,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    store: dict[str, uuid.UUID] = {}
    script = Script(clock)
    script.at(30, detects(sessions, target_id, store))
    script.at(60, raises("database went away"))
    chaos.fail_stop = True

    with pytest.raises(RuntimeError, match="database went away"):
        await runner.run(scenario, TARGET, RESOURCE)

    assert chaos.stops == [RESOURCE]
    [run] = await load_runs(sessions)
    assert run.error == "database went away"


async def test_cpu_burn_runs_end_to_end_and_stops_the_burn(
    runner: ScenarioRunner,
    clock: FakeClock,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    scenario = load_scenario(SCENARIOS_DIR / "high-cpu.yaml")
    store: dict[str, uuid.UUID] = {}
    script = Script(clock)
    script.at(30, detects(sessions, target_id, store))
    script.at(90, moves_to(sessions, store, "ESCALATED", "cpu_runaway_process"))

    outcome = await runner.run(scenario, TARGET)

    assert outcome.status == "completed"
    assert outcome.detection_seconds == 30.0
    assert outcome.root_cause_match is True
    assert chaos.events == ["start:cpu_burn", "stop:cpu_burn"]
    assert chaos.active is False
    [run] = await load_runs(sessions)
    assert run.scenario == "high-cpu"
    assert run.resource_id == "host:demo-1"
    assert run.ground_truth["resource_id"] is None


async def test_disk_fill_failure_stops_the_fill(
    runner: ScenarioRunner,
    clock: FakeClock,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    scenario = load_scenario(SCENARIOS_DIR / "disk-pressure.yaml")
    store: dict[str, uuid.UUID] = {}
    script = Script(clock)
    script.at(30, detects(sessions, target_id, store))
    script.at(60, raises("database went away"))

    with pytest.raises(RuntimeError, match="database went away"):
        await runner.run(scenario, TARGET)

    assert chaos.events == ["start:disk_fill", "stop:disk_fill"]
    assert chaos.active is False
    [run] = await load_runs(sessions)
    assert run.scenario == "disk-pressure"
    assert run.status == "failed"


async def test_failed_disk_fill_start_still_attempts_the_stop(
    runner: ScenarioRunner,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    scenario = load_scenario(SCENARIOS_DIR / "disk-pressure.yaml")
    chaos.fail_start = True

    with pytest.raises(ChaosError, match="INTERNAL"):
        await runner.run(scenario, TARGET)

    assert chaos.events == ["start:disk_fill", "stop:disk_fill"]
    [run] = await load_runs(sessions)
    assert run.status == "failed"


async def test_stopping_an_idle_disk_fill_reports_nothing_active(
    runner: ScenarioRunner, chaos: FakeChaos
) -> None:
    assert await runner.stop_injection("disk_fill", "host:demo-1") is False
    assert chaos.events == ["stop:disk_fill"]


async def test_memory_leak_runs_end_to_end_and_resets_the_app(
    runner: ScenarioRunner,
    clock: FakeClock,
    chaos: FakeChaos,
    sessions: SessionFactory,
    target_id: uuid.UUID,
) -> None:
    scenario = load_scenario(SCENARIOS_DIR / "memory-leak.yaml")
    store: dict[str, uuid.UUID] = {}
    script = Script(clock)
    script.at(420, detects(sessions, target_id, store))
    script.at(480, moves_to(sessions, store, "RESOLVED", "memory_leak"))

    outcome = await runner.run(scenario, TARGET)

    assert outcome.status == "completed"
    assert outcome.root_cause_match is True
    assert chaos.events == ["start:app_fault:memory_leak", "stop:app_fault"]
    assert chaos.starts == [("svc:demo-shop", 900)]
    assert chaos.stops == ["svc:demo-shop"]
    [run] = await load_runs(sessions)
    assert run.resource_id == "svc:demo-shop"
