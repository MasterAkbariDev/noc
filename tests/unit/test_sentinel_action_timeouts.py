from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID, uuid4

import pytest

from noc_sentinel.action_store import ActionStore
from noc_sentinel.actions import (
    ACTION_TIMEOUT_SECONDS,
    MAX_SERVICE_ACTION_SECONDS,
    ActionExecutor,
    service_action_timeout,
)
from noc_sentinel.config import ActionsConfig
from noc_sentinel.tools.systemd import timespan_seconds
from noc_shared.actions import ActionRequest, ServiceActionType, compute_action_hash
from tests.support.builders import DEMO_SHOP, FakeSystemctl, sentinel_config

NOW = datetime(2026, 10, 16, 18, 0, tzinfo=UTC)
INCIDENT = UUID("5b1e2c3d-4f5a-4b6c-8d7e-9f0a1b2c3d4e")


class TimeoutSystemctl(FakeSystemctl):
    def __init__(self, stop: str, start: str) -> None:
        super().__init__(active_state="active")
        self.timeouts = {"TimeoutStopUSec": stop, "TimeoutStartUSec": start}

    def show(self, unit: str, properties: tuple[str, ...]) -> dict[str, str]:
        values = super().show(unit, properties)
        return {**values, **{key: self.timeouts[key] for key in properties if key in self.timeouts}}


class TimingRunner:
    def __init__(self) -> None:
        self.timeouts: list[int] = []

    def run(self, argv: tuple[str, ...], timeout_seconds: int) -> int:
        self.timeouts.append(timeout_seconds)
        return 0


@pytest.mark.parametrize(
    ("text", "seconds"),
    [
        ("1min 30s", 90.0),
        ("90s", 90.0),
        ("500ms", 0.5),
        ("2h", 7200.0),
        ("1min 30s 250ms", 90.25),
        ("infinity", float("inf")),
        ("", None),
        ("soon", None),
        ("1min soon", None),
        (None, None),
    ],
)
def test_systemd_timespans_are_read_as_seconds(text: str | None, seconds: float | None) -> None:
    assert timespan_seconds(text) == seconds


@pytest.mark.parametrize(
    ("action", "stop", "start", "expected"),
    [
        ("restart_service", "1min 30s", "1min 30s", 195),
        ("restart_service", "1min 30s", "0", 105),
        ("start_service", "1min 30s", "10s", ACTION_TIMEOUT_SECONDS),
        ("start_service", "1min 30s", "1min", 75),
        ("restart_service", "5s", "5s", ACTION_TIMEOUT_SECONDS),
        ("restart_service", "infinity", "1min 30s", MAX_SERVICE_ACTION_SECONDS),
        ("restart_service", "10min", "10min", MAX_SERVICE_ACTION_SECONDS),
        ("restart_service", "garbage", "nonsense", ACTION_TIMEOUT_SECONDS),
    ],
)
def test_service_actions_wait_as_long_as_the_unit_may_take(
    action: ServiceActionType, stop: str, start: str, expected: int
) -> None:
    unit = {"TimeoutStopUSec": stop, "TimeoutStartUSec": start}
    assert service_action_timeout(action, unit) == expected


def test_a_restart_gets_the_units_stop_and_start_time(tmp_path: Path) -> None:
    config = sentinel_config(tmp_path).model_copy(update={"actions": ActionsConfig(enabled=True)})
    runner = TimingRunner()
    executor = ActionExecutor(
        config,
        TimeoutSystemctl(stop="1min 30s", start="1min 30s"),
        runner,
        ActionStore(tmp_path / "actions.db"),
        lambda: NOW,
        lambda _: None,
    )
    request = ActionRequest(
        action_id=uuid4(),
        attempt_id=uuid4(),
        incident_id=INCIDENT,
        attempt=1,
        action_hash=compute_action_hash("restart_service", "demo-1", DEMO_SHOP, {}, INCIDENT, 1),
        resource_id=DEMO_SHOP,
        auto_policy_ref="policy:test",
    )
    result = executor.execute("restart_service", request).result
    assert result.status == "succeeded"
    assert runner.timeouts == [195]
