from noc.api.story import build_advice
from noc.db.models import Incident
from noc.domain.incident_status import IncidentStatus
from noc.reporting.operator_guide import (
    GuideContext,
    load_guide,
    steps_after_fix,
    steps_to_fix,
)
from noc_shared.taxonomy import RootCauseCode

SHOP = GuideContext(unit="demo-shop.service", mount="/srv/demo-data")


def commands(steps: list) -> list[str]:
    return [step.command for step in steps if step.command]


def test_the_shipped_guide_loads_and_covers_every_root_cause() -> None:
    guide = load_guide()
    missing = {code for code in RootCauseCode if code is not RootCauseCode.UNKNOWN} - set(
        guide.root_causes
    )
    assert missing == set()


def test_a_known_cause_gives_its_own_steps_with_the_real_unit() -> None:
    steps = steps_to_fix(load_guide(), "service_crashed", "ServiceDown", SHOP)
    assert "systemctl status demo-shop.service" in commands(steps)
    assert "sudo systemctl start demo-shop.service" in commands(steps)


def test_an_unknown_cause_falls_back_to_the_alert_steps() -> None:
    steps = steps_to_fix(load_guide(), "unknown", "DiskAlmostFull", SHOP)
    assert "df -h /srv/demo-data" in commands(steps)


def test_an_unknown_cause_and_alert_gives_the_general_steps() -> None:
    steps = steps_to_fix(load_guide(), None, "SomethingNew", GuideContext())
    assert steps == load_guide().fallback


def test_missing_context_leaves_a_readable_placeholder() -> None:
    steps = steps_to_fix(load_guide(), "service_crashed", None, GuideContext())
    assert "systemctl status <service>" in commands(steps)


def test_a_restart_that_hides_a_leak_says_so_after_the_fix() -> None:
    steps = steps_after_fix(load_guide(), "memory_leak", SHOP)
    assert steps
    assert "developers" in steps[0].text
    assert steps_after_fix(load_guide(), "transient_spike", SHOP) == []


def test_an_escalated_incident_gets_the_guide_in_its_advice() -> None:
    incident = Incident(title="x", status="ESCALATED", escalation_reason="no_allowed_action")
    advice = build_advice(
        incident, IncidentStatus.ESCALATED, "disk_full_logs", None, "DiskAlmostFull", SHOP
    )
    assert "sudo journalctl --vacuum-size=200M" in commands(advice.steps)
