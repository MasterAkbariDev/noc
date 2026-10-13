from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from noc.agents.supervisor import (
    AlertRoute,
    InvestigationPlan,
    RoutingTable,
    load_routing,
    plan_investigation,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
ROUTING_PATH = REPO_ROOT / "noc/src/noc/orchestration/routing.yaml"
RULES_DIR = REPO_ROOT / "deploy/noc/prometheus/rules"

ALL_FOUR = ["metrics", "logs", "network", "security"]


def table(**alerts: list[str]) -> RoutingTable:
    return RoutingTable(
        alerts={name: AlertRoute(specialists=specialists) for name, specialists in alerts.items()}
    )


def alert_names_in_rules() -> set[str]:
    names: set[str] = set()
    for rules_file in RULES_DIR.glob("*.yml"):
        document = yaml.safe_load(rules_file.read_text())
        for group in document["groups"]:
            for rule in group["rules"]:
                if "alert" in rule:
                    names.add(rule["alert"])
    return names


@pytest.fixture(scope="module")
def routing() -> RoutingTable:
    return load_routing(ROUTING_PATH)


def test_real_routing_file_loads_with_known_specialists(routing: RoutingTable) -> None:
    specialists = {name for route in routing.alerts.values() for name in route.specialists}
    assert specialists <= set(ALL_FOUR)
    assert "HostCPUSaturated" in routing.alerts


def test_every_alert_rule_has_a_routing_entry(routing: RoutingTable) -> None:
    rule_names = alert_names_in_rules()
    assert rule_names, "no alert rules found under deploy/noc/prometheus/rules"
    missing = sorted(rule_names - set(routing.alerts))
    assert missing == []


@pytest.mark.parametrize(
    ("alertnames", "expected"),
    [
        (["HostCPUSaturated"], ["metrics", "logs"]),
        (["ServiceDown"], ["metrics", "logs", "network"]),
        (["SSHBruteForce"], ["logs", "network", "security"]),
        (["TargetDown"], ["metrics", "network"]),
        (["HostCPUSaturated", "ServiceDown"], ["metrics", "logs", "network"]),
        (["SSHBruteForce", "DiskAlmostFull"], ["metrics", "logs", "network", "security"]),
    ],
)
def test_known_alerts_use_union_of_base_sets(
    routing: RoutingTable, alertnames: list[str], expected: list[str]
) -> None:
    plan = plan_investigation(alertnames, routing)
    assert plan.specialists == expected
    assert plan.not_selected == [name for name in ALL_FOUR if name not in expected]


def test_unknown_alert_selects_all_four(routing: RoutingTable) -> None:
    plan = plan_investigation(["SomethingNew"], routing)
    assert plan.specialists == ALL_FOUR
    assert plan.not_selected == []


def test_unknown_alert_widens_known_alert_to_all_four(routing: RoutingTable) -> None:
    plan = plan_investigation(["HostCPUSaturated", "SomethingNew"], routing)
    assert plan.specialists == ALL_FOUR


def test_empty_alert_list_selects_all_four(routing: RoutingTable) -> None:
    plan = plan_investigation([], routing)
    assert plan.specialists == ALL_FOUR


def test_duplicate_alerts_give_the_same_plan_as_one(routing: RoutingTable) -> None:
    once = plan_investigation(["ServiceDown"], routing)
    twice = plan_investigation(["ServiceDown", "ServiceDown"], routing)
    assert twice == once


def test_order_is_fixed_regardless_of_alert_order(routing: RoutingTable) -> None:
    first = plan_investigation(["SSHBruteForce", "HostCPUSaturated"], routing)
    second = plan_investigation(["HostCPUSaturated", "SSHBruteForce"], routing)
    assert first.specialists == second.specialists == ALL_FOUR


def test_focus_questions_are_merged_without_duplicates() -> None:
    routing_table = RoutingTable(
        alerts={
            "A": AlertRoute(
                specialists=["metrics", "logs"],
                focus={"metrics": ["q1", "q2"]},
            ),
            "B": AlertRoute(
                specialists=["metrics"],
                focus={"metrics": ["q2", "q3"]},
            ),
        }
    )
    plan = plan_investigation(["A", "B"], routing_table)
    assert plan.focus == {"metrics": ["q1", "q2", "q3"]}


def test_plan_lists_unselected_specialists() -> None:
    routing_table = table(A=["logs"])
    plan = plan_investigation(["A"], routing_table)
    assert plan == InvestigationPlan(
        specialists=["logs"], focus={}, not_selected=["metrics", "network", "security"]
    )


def test_unknown_specialist_in_yaml_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "routing.yaml"
    path.write_text("alerts:\n  X: {specialists: [database]}\n")
    with pytest.raises(ValidationError):
        load_routing(path)


def test_focus_for_unselected_specialist_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "routing.yaml"
    path.write_text("alerts:\n  X:\n    specialists: [logs]\n    focus: {metrics: [why]}\n")
    with pytest.raises(ValidationError):
        load_routing(path)


def test_unknown_yaml_field_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "routing.yaml"
    path.write_text("alerts:\n  X: {specialists: [logs], extra: 1}\n")
    with pytest.raises(ValidationError):
        load_routing(path)
