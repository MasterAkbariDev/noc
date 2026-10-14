from pathlib import Path
from typing import cast

import httpx
import pytest
import yaml

from noc.agents.schemas import FindingCategory
from noc.config import PACKAGE_DIR
from noc.orchestration.runbook import (
    OK_MARKER,
    RUNBOOK_FILE,
    Runbook,
    RunbookEntry,
    entry_for,
    excerpt_for,
    load_runbook,
    resolve_arguments,
)
from noc.policy.loader import load_policy
from noc.tools.catalog import RUNBOOK, build_read_tools
from noc.tools.recorder import ToolCallRecorder
from noc.tools.registry import ToolRegistry
from noc.tools.sentinel_client import SentinelDirectory
from noc_shared.taxonomy import RootCauseCode

ROUTING_FILE = PACKAGE_DIR / "orchestration" / "routing.yaml"
POLICY_FILE = PACKAGE_DIR / "policy" / "default_policy.yaml"


def service_entry() -> RunbookEntry:
    return RunbookEntry(
        root_cause=RootCauseCode.SERVICE_CRASHED,
        tool="get_service_status",
        args={"resource_id": "$resource"},
        category=FindingCategory.SERVICE,
        excerpt_key="active_state",
    )


def test_shipped_runbook_loads() -> None:
    runbook = load_runbook(RUNBOOK_FILE)
    assert "ServiceDown" in runbook.alerts
    assert runbook.alerts["ServiceDown"].root_cause is RootCauseCode.SERVICE_CRASHED


def test_every_runbook_alert_is_a_known_alert() -> None:
    routing = yaml.safe_load(ROUTING_FILE.read_text())["alerts"]
    assert set(load_runbook().alerts) <= set(routing)


def test_every_runbook_tool_is_available_to_the_runbook_agent() -> None:
    sentinels = SentinelDirectory(Path("/nonexistent"), cast(httpx.AsyncClient, None))
    registry = ToolRegistry(build_read_tools(sentinels), cast(ToolCallRecorder, None))
    available = set(registry.names_for(RUNBOOK))
    assert {entry.tool for entry in load_runbook().alerts.values()} <= available


def test_runbook_agent_has_no_other_tools() -> None:
    sentinels = SentinelDirectory(Path("/nonexistent"), cast(httpx.AsyncClient, None))
    registry = ToolRegistry(build_read_tools(sentinels), cast(ToolCallRecorder, None))
    assert set(registry.names_for(RUNBOOK)) == {
        "get_service_status",
        "get_cpu_usage",
        "get_memory_usage",
        "get_disk_usage",
    }


def test_runbook_root_causes_are_all_actionable_or_deliberately_not() -> None:
    policy = load_policy(POLICY_FILE)
    for alertname, entry in load_runbook().alerts.items():
        assert policy.candidate_actions(entry.root_cause.value), alertname


def test_first_known_alert_wins_in_the_order_given() -> None:
    runbook = Runbook(alerts={"A": service_entry(), "B": service_entry()})
    assert entry_for(runbook, ["Unknown", "B", "A"]) is not None
    found = entry_for(runbook, ["Unknown", "B", "A"])
    assert found is not None
    assert found[0] == "B"


def test_unknown_alerts_have_no_entry() -> None:
    assert entry_for(load_runbook(), ["SomethingNew"]) is None


def test_label_arguments_are_filled_from_the_alert() -> None:
    assert resolve_arguments(service_entry(), {"resource": "svc:demo-shop"}) == {
        "resource_id": "svc:demo-shop"
    }


def test_missing_label_means_the_entry_cannot_run() -> None:
    assert resolve_arguments(service_entry(), {}) is None
    assert resolve_arguments(service_entry(), {"resource": ""}) is None


def test_literal_arguments_pass_through() -> None:
    entry = service_entry().model_copy(update={"args": {"sort_by": "cpu"}})
    assert resolve_arguments(entry, {}) == {"sort_by": "cpu"}


def test_excerpt_quotes_the_key_and_value_exactly_as_the_tool_result_prints_them() -> None:
    assert excerpt_for(service_entry(), {"active_state": "failed"}) == '"active_state": "failed"'
    percent = service_entry().model_copy(update={"excerpt_key": "percent"})
    assert excerpt_for(percent, {"percent": 91.5}) == '"percent": 91.5'


@pytest.mark.parametrize("data", [None, {}, {"other": 1}])
def test_excerpt_falls_back_to_the_ok_marker(data: dict[str, object] | None) -> None:
    assert excerpt_for(service_entry(), data) == OK_MARKER


def test_entries_without_a_key_use_the_ok_marker() -> None:
    entry = service_entry().model_copy(update={"excerpt_key": None})
    assert excerpt_for(entry, {"active_state": "failed"}) == OK_MARKER


def test_security_alerts_are_left_to_a_person() -> None:
    assert "SSHBruteForce" not in load_runbook().alerts
    assert entry_for(load_runbook(), ["SSHBruteForce", "SSHLoginFromNewSource"]) is None
