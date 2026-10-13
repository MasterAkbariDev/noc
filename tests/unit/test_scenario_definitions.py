import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from noc.scenarios.definitions import load_scenario, load_scenarios, parse_scenario
from noc_shared.taxonomy import RootCauseCode

SCENARIOS_DIR = Path(__file__).resolve().parents[2] / "scenarios"

VALID: dict[str, Any] = {
    "name": "service-down",
    "description": "stop demo-shop",
    "injection": {"type": "service_down", "resource_id": "svc:demo-shop", "ttl_seconds": 600},
    "ground_truth": {
        "root_cause_code": "service_crashed",
        "resource_id": "svc:demo-shop",
        "acceptable_actions": ["start_service", "restart_service"],
        "expected_outcome": "escalated",
    },
}


def test_every_scenario_file_validates() -> None:
    files = sorted(SCENARIOS_DIR.glob("*.yaml"))
    scenarios = load_scenarios(SCENARIOS_DIR)
    assert files
    assert len(scenarios) == len(files)


def test_every_scenario_root_cause_is_in_the_taxonomy() -> None:
    for scenario in load_scenarios(SCENARIOS_DIR).values():
        assert scenario.ground_truth.root_cause_code in set(RootCauseCode)


def test_service_down_scenario_has_the_documented_defaults() -> None:
    scenario = load_scenario(SCENARIOS_DIR / "service-down.yaml")
    assert scenario.name == "service-down"
    assert scenario.injection.type == "service_down"
    assert scenario.detection_timeout_seconds == 240
    assert scenario.outcome_timeout_seconds == 600
    assert scenario.ground_truth.root_cause_code == "service_crashed"
    assert scenario.ground_truth.expected_outcome == "escalated"


def test_defaults_apply_when_timeouts_are_omitted() -> None:
    scenario = parse_scenario(copy.deepcopy(VALID))
    assert scenario.detection_timeout_seconds == 240
    assert scenario.outcome_timeout_seconds == 600


def test_unknown_root_cause_is_rejected() -> None:
    raw = copy.deepcopy(VALID)
    raw["ground_truth"]["root_cause_code"] = "gremlins"
    with pytest.raises(ValidationError):
        parse_scenario(raw)


def test_ttl_must_cover_the_detection_timeout() -> None:
    raw = copy.deepcopy(VALID)
    raw["injection"]["ttl_seconds"] = 120
    with pytest.raises(ValidationError, match="detection_timeout_seconds"):
        parse_scenario(raw)


def test_ground_truth_resource_must_match_the_injection() -> None:
    raw = copy.deepcopy(VALID)
    raw["ground_truth"]["resource_id"] = "svc:other"
    with pytest.raises(ValidationError, match="resource_id"):
        parse_scenario(raw)


def test_unknown_keys_are_rejected() -> None:
    raw = copy.deepcopy(VALID)
    raw["shell"] = "rm -rf /"
    with pytest.raises(ValidationError):
        parse_scenario(raw)


def test_unknown_injection_type_is_rejected() -> None:
    raw = copy.deepcopy(VALID)
    raw["injection"]["type"] = "cpu_burn"
    with pytest.raises(ValidationError):
        parse_scenario(raw)
