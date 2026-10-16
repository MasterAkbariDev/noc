import uuid
from datetime import UTC, datetime

from noc.api.overview import fix_kind, fixed_item
from noc.db.models import ActionRow, Incident

RESOLVED_AT = datetime(2026, 10, 16, 8, 30, tzinfo=UTC)


def incident(status: str) -> Incident:
    return Incident(
        id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        status=status,
        severity="critical",
        title="demo-shop.service is down",
        trace_id="t",
        opened_at=RESOLVED_AT,
        resolved_at=RESOLVED_AT,
    )


def action(
    authorization: str, action_type: str = "start_service", resource_id: str = "svc:demo-shop"
) -> ActionRow:
    return ActionRow(
        action_type=action_type,
        resource_id=resource_id,
        status="succeeded",
        authorization=authorization,
    )


def test_an_incident_that_resolved_on_its_own_is_by_itself() -> None:
    assert fix_kind(incident("SELF_RESOLVED"), []) == "by_itself"


def test_a_resolved_incident_without_a_succeeded_action_is_by_itself() -> None:
    assert fix_kind(incident("RESOLVED"), []) == "by_itself"


def test_a_fix_the_policy_authorized_is_automatic() -> None:
    assert fix_kind(incident("RESOLVED"), [action("policy:v3")]) == "automatic"


def test_a_fix_a_person_approved_is_approved() -> None:
    assert fix_kind(incident("CLOSED"), [action("approval:1234")]) == "approved"


def test_the_automatic_sentence_names_the_action_and_the_resource() -> None:
    item = fixed_item(incident("RESOLVED"), "demo-1", [action("policy:v3")])
    assert item.kind == "automatic"
    assert item.target == "demo-1"
    assert item.resolved_at == RESOLVED_AT
    assert item.sentence == (
        "The NOC chose to start the service on demo-shop and did it on its own. "
        "The check afterwards passed."
    )


def test_the_approved_sentence_says_a_person_approved_the_plan() -> None:
    item = fixed_item(incident("RESOLVED"), "demo-1", [action("approval:1234")])
    assert item.sentence == (
        "A person approved the plan to start the service on demo-shop. "
        "The NOC did it and the check afterwards passed."
    )


def test_two_fixes_are_told_in_the_order_they_ran() -> None:
    first = action("policy:v3", "throttle_cpu", "job:report-gen")
    second = action("policy:v3", "stop_service", "job:report-gen")
    item = fixed_item(incident("RESOLVED"), "demo-1", [first, second])
    assert item.sentence.startswith(
        "The NOC chose to limit the CPU use on report-gen "
        "and then stop the service on report-gen and did it on its own."
    )


def test_the_by_itself_sentence_names_no_action() -> None:
    item = fixed_item(incident("SELF_RESOLVED"), "demo-1", [])
    assert item.sentence == "The problem went away on its own before the NOC had to act."
