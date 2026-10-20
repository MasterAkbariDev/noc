import uuid
from datetime import UTC, datetime

import pytest

from noc.db.models import IncidentEvent
from noc.notify.outbox import event_kind, headline, wanted
from noc.notify.settings import NotifyEvents
from noc.notify.telegram import scrub, valid_token, valid_user_handle

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


def test_bot_tokens_and_user_handles_are_checked() -> None:
    assert valid_token(TOKEN)
    assert not valid_token("not-a-token")
    assert not valid_token("123:short")
    assert valid_user_handle("123456789")
    assert valid_user_handle("@noc_admin")
    assert not valid_user_handle("-1001234567890")
    assert not valid_user_handle("noc admin")
    assert not valid_user_handle("@ab")


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


def test_headlines_name_the_event() -> None:
    assert headline(event("incident_opened")) == "New incident"
    assert headline(event("approval_requested")) == "Approval needed"
    assert headline(event("state_changed", {"to": "ESCALATED"})) == "Escalated to a person"
    assert headline(event("state_changed", {"to": "SELF_RESOLVED"})) == "Resolved on its own"
