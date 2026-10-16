import copy
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from noc.scenarios.definitions import (
    AppFaultInjection,
    CpuBurnInjection,
    DiskFillInjection,
    injection_summary,
    load_scenario,
    load_scenarios,
    parse_scenario,
)
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


def test_cpu_and_disk_scenario_files_match_the_plan() -> None:
    high_cpu = load_scenario(SCENARIOS_DIR / "high-cpu.yaml")
    disk = load_scenario(SCENARIOS_DIR / "disk-pressure.yaml")
    assert isinstance(high_cpu.injection, CpuBurnInjection)
    assert (high_cpu.injection.workers, high_cpu.injection.ttl_seconds) == (2, 900)
    assert high_cpu.ground_truth.root_cause_code == "cpu_runaway_process"
    assert high_cpu.ground_truth.acceptable_actions == ["throttle_cpu", "stop_service"]
    assert high_cpu.ground_truth.resource_id == "job:report-gen"
    assert isinstance(disk.injection, DiskFillInjection)
    assert (disk.injection.target_percent, disk.injection.ttl_seconds) == (92, 900)
    assert disk.ground_truth.root_cause_code == "disk_full_logs"
    assert disk.ground_truth.acceptable_actions == ["rotate_logs", "vacuum_journal"]
    assert disk.ground_truth.resource_id == "dir:demo-data"
    assert high_cpu.ground_truth.expected_outcome == "resolved"
    assert disk.ground_truth.expected_outcome == "resolved"


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
    raw["injection"]["type"] = "gremlins"
    with pytest.raises(ValidationError):
        parse_scenario(raw)


def cpu_scenario(**injection: Any) -> dict[str, Any]:
    raw = copy.deepcopy(VALID)
    raw["name"] = "high-cpu"
    raw["injection"] = {"type": "cpu_burn", "workers": 2, "ttl_seconds": 900, **injection}
    raw["ground_truth"] = {
        "root_cause_code": "cpu_runaway_process",
        "resource_id": None,
        "acceptable_actions": ["kill_process"],
        "expected_outcome": "escalated",
    }
    return raw


def disk_scenario(**injection: Any) -> dict[str, Any]:
    raw = cpu_scenario()
    raw["name"] = "disk-pressure"
    raw["injection"] = {"type": "disk_fill", "target_percent": 92, "ttl_seconds": 900, **injection}
    raw["ground_truth"]["root_cause_code"] = "disk_full_logs"
    return raw


def test_cpu_burn_injection_parses_without_a_resource() -> None:
    scenario = parse_scenario(cpu_scenario())
    assert isinstance(scenario.injection, CpuBurnInjection)
    assert scenario.injection.workers == 2
    assert scenario.ground_truth.resource_id is None


def test_disk_fill_injection_parses_without_a_resource() -> None:
    scenario = parse_scenario(disk_scenario())
    assert isinstance(scenario.injection, DiskFillInjection)
    assert scenario.injection.target_percent == 92
    assert scenario.ground_truth.resource_id is None


@pytest.mark.parametrize("workers", [0, 9])
def test_cpu_workers_out_of_range_are_rejected(workers: int) -> None:
    with pytest.raises(ValidationError):
        parse_scenario(cpu_scenario(workers=workers))


@pytest.mark.parametrize("target_percent", [49, 96])
def test_disk_target_out_of_range_is_rejected(target_percent: int) -> None:
    with pytest.raises(ValidationError):
        parse_scenario(disk_scenario(target_percent=target_percent))


def test_cpu_injection_rejects_an_extra_field() -> None:
    with pytest.raises(ValidationError):
        parse_scenario(cpu_scenario(unexpected="x"))


def test_disk_injection_rejects_a_service_field() -> None:
    with pytest.raises(ValidationError):
        parse_scenario(disk_scenario(resource_id="svc:demo-shop"))


def test_cpu_injection_must_still_cover_the_detection_timeout() -> None:
    with pytest.raises(ValidationError, match="detection_timeout_seconds"):
        parse_scenario(cpu_scenario(ttl_seconds=120))


def test_injection_summary_describes_each_kind() -> None:
    assert injection_summary(parse_scenario(VALID).injection) == "svc:demo-shop"
    assert injection_summary(parse_scenario(cpu_scenario()).injection) == "workers=2"
    assert injection_summary(parse_scenario(disk_scenario()).injection) == "fill to 92%"


def leak_scenario(**injection: Any) -> dict[str, Any]:
    raw = copy.deepcopy(VALID)
    raw["name"] = "memory-leak"
    raw["injection"] = {
        "type": "app_fault",
        "resource_id": "svc:demo-shop",
        "fault": "memory_leak",
        "ttl_seconds": 900,
        **injection,
    }
    raw["ground_truth"]["root_cause_code"] = "memory_leak"
    return raw


def test_memory_leak_scenario_file_matches_the_plan() -> None:
    scenario = load_scenario(SCENARIOS_DIR / "memory-leak.yaml")
    assert isinstance(scenario.injection, AppFaultInjection)
    assert scenario.injection.fault == "memory_leak"
    assert scenario.injection.resource_id == "svc:demo-shop"
    assert scenario.ground_truth.root_cause_code == "memory_leak"
    assert scenario.ground_truth.acceptable_actions == ["restart_service"]
    assert scenario.ground_truth.expected_outcome == "resolved"


def test_app_fault_rejects_an_unknown_fault() -> None:
    with pytest.raises(ValidationError):
        parse_scenario(leak_scenario(fault="fork_bomb"))


def test_app_fault_ground_truth_must_name_the_injected_service() -> None:
    raw = leak_scenario()
    raw["ground_truth"]["resource_id"] = "svc:other"
    with pytest.raises(ValidationError, match="resource_id"):
        parse_scenario(raw)


def test_app_fault_summary_names_the_fault_and_the_service() -> None:
    summary = injection_summary(parse_scenario(leak_scenario()).injection)
    assert summary == "memory_leak in svc:demo-shop"
