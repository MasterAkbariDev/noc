import uuid
from datetime import UTC, datetime

import pytest

from noc.db.models import Incident, IncidentEvent, Target
from noc.notify.outbox import event_kind, message_for, wanted
from noc.notify.settings import NotifyEvents
from noc.notify.telegram import scrub, valid_chat_id, valid_token

TOKEN = "123456789:AAH-abcdefghijklmnopqrstuvwxyz012345"


def event(kind: str, payload: dict[str, object] | None = None) -> IncidentEvent:
    return IncidentEvent(
        id=1,
        incident_id=uuid.uuid4(),
        ts=datetime(2026, 10, 15, tzinfo=UTC),
        type=kind,
        actor="test",
        payload=payload or {},
    )


def incident(**changes: object) -> Incident:
    values: dict[str, object] = {
        "id": uuid.UUID("11111111-2222-3333-4444-555555555555"),
        "title": "ServiceDown on demo-1/svc:demo-shop",
        "status": "ESCALATED",
        "escalation_reason": "unknown_root_cause",
        "root_cause_code": "service_crashed",
        "confidence": 0.85,
    }
    values.update(changes)
    return Incident(**values)


TARGET = Target(name="demo-1", environment="lab")


def test_bot_tokens_and_chat_ids_are_checked() -> None:
    assert valid_token(TOKEN)
    assert not valid_token("not-a-token")
    assert not valid_token("123:short")
    assert valid_chat_id("-1001234567890")
    assert valid_chat_id("42")
    assert valid_chat_id("@noc_alerts")
    assert not valid_chat_id("noc alerts")
    assert not valid_chat_id("@ab")


def test_scrub_removes_the_token() -> None:
    assert scrub(f"POST /bot{TOKEN}/sendMessage failed", TOKEN) == "POST /bot***/sendMessage failed"


@pytest.mark.parametrize(
    ("kind", "payload", "expected"),
    [
        ("incident_opened", {}, "opened"),
        ("approval_requested", {}, "approval"),
        ("approval_expired", {}, "approval"),
        ("state_changed", {"to": "ESCALATED"}, "escalated"),
        ("state_changed", {"to": "RESOLVED"}, "resolved"),
        ("state_changed", {"to": "SELF_RESOLVED"}, "resolved"),
        ("state_changed", {"to": "DIAGNOSED"}, None),
        ("report_generated", {}, None),
    ],
)
def test_event_kinds(kind: str, payload: dict[str, object], expected: str | None) -> None:
    assert event_kind(event(kind, payload)) == expected


def test_only_chosen_kinds_are_wanted() -> None:
    choice = NotifyEvents(opened=False, approval=True, escalated=True, resolved=False)
    assert not wanted(event("incident_opened"), choice)
    assert wanted(event("approval_requested"), choice)
    assert not wanted(event("state_changed", {"to": "RESOLVED"}), choice)
    assert not wanted(event("report_generated"), choice)


def test_escalation_message_has_reason_cause_and_link() -> None:
    text = message_for(
        event("state_changed", {"to": "ESCALATED", "reason": "unknown_root_cause"}),
        incident(),
        TARGET,
        "https://noc.example",
    )
    assert text.splitlines() == [
        "[NOC] Escalated to a person: ServiceDown on demo-1/svc:demo-shop",
        "Server: demo-1 (lab)",
        "Reason: unknown root cause",
        "Root cause: service crashed (85%)",
        "https://noc.example/incidents/11111111-2222-3333-4444-555555555555",
    ]


def test_message_without_panel_url_or_diagnosis_stays_short() -> None:
    text = message_for(
        event("approval_requested"),
        incident(root_cause_code=None, confidence=None, escalation_reason=None),
        TARGET,
        "",
    )
    assert text.splitlines() == [
        "[NOC] Approval needed: ServiceDown on demo-1/svc:demo-shop",
        "Server: demo-1 (lab)",
    ]
