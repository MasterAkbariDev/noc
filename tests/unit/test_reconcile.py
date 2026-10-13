from noc.detection.reconcile import OpenAlertState, plan_reconciliation
from tests.support.builders import prometheus_alert


def test_new_alert_is_detected() -> None:
    alert = prometheus_alert()
    plan = plan_reconciliation([], [alert], missing_polls_to_resolve=2)
    assert plan.new == [alert]


def test_known_alert_is_still_firing() -> None:
    alert = prometheus_alert()
    plan = plan_reconciliation([OpenAlertState(alert.fingerprint, 1)], [alert], 2)
    assert plan.still_firing == [alert]
    assert plan.new == []


def test_one_missing_poll_does_not_resolve() -> None:
    plan = plan_reconciliation([OpenAlertState("abc", 0)], [], 2)
    assert plan.missed == ["abc"]
    assert plan.resolved == []


def test_second_missing_poll_resolves() -> None:
    plan = plan_reconciliation([OpenAlertState("abc", 1)], [], 2)
    assert plan.resolved == ["abc"]


def test_fingerprint_ignores_label_order() -> None:
    first = prometheus_alert()
    second = first.model_copy(update={"labels": dict(reversed(list(first.labels.items())))})
    assert first.fingerprint == second.fingerprint
