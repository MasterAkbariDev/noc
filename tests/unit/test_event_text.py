import pytest

from noc.reporting.event_text import event_text


@pytest.mark.parametrize(
    ("event_type", "actor", "payload", "expected"),
    [
        (
            "incident_opened",
            "correlator",
            {"alertname": "ServiceDown", "value": "0e+00"},
            "The alert “ServiceDown” fired and opened this incident",
        ),
        (
            "state_changed",
            "policy",
            {"from": "PLANNED", "to": "ESCALATED", "reason": "no_allowed_action"},
            "Status: Planning the fix → Needs you, because no automatic action is allowed",
        ),
        (
            "investigation_planned",
            "supervisor",
            {"specialists": ["metrics", "logs", "network"], "focus": {}},
            "Sent the metrics, logs and network specialists to look",
        ),
        (
            "specialist_finished",
            "metrics",
            {"findings": 1, "dropped_findings": 1, "dropped": []},
            "The metrics specialist finished with 1 finding; 1 more finding thrown away",
        ),
        (
            "approval_requested",
            "planner",
            {"action_type": "start_service", "resource_id": "svc:demo-shop"},
            "Asked a person to approve: Start service on demo-shop",
        ),
        (
            "approval_decided",
            "lab-test",
            {
                "decision": "approved",
                "action_type": "start_service",
                "resource_id": "svc:demo-shop",
                "comment": "Chaos test approval",
            },
            "lab-test approved: Start service on demo-shop (Chaos test approval)",
        ),
        (
            "action_succeeded",
            "executor",
            {"action_type": "start_service", "resource_id": "svc:demo-shop"},
            "Start service on demo-shop: done, it worked",
        ),
        (
            "verification_passed",
            "verifier",
            {"service_active": True, "alerts_resolved": True},
            "Checked the fix: the service is running and the alert has stopped",
        ),
        ("report_generated", "reporter", {}, "Wrote the incident report"),
        ("something_new", "x", {}, "Something new"),
    ],
)
def test_events_read_as_sentences(
    event_type: str, actor: str, payload: dict[str, object], expected: str
) -> None:
    assert event_text(event_type, actor, payload).startswith(expected)


def test_a_reasonless_status_change_has_no_because() -> None:
    text = event_text("state_changed", "supervisor", {"from": "NEW", "to": "INVESTIGATING"})
    assert "because" not in text
