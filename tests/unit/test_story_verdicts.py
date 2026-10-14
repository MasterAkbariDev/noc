import uuid
from datetime import UTC, datetime

import pytest

from noc.api.schemas import StoryAdvice
from noc.api.story import VERDICT_BY_STATUS, action_verdict, build_advice, build_headline, did_text
from noc.db.models import ActionRow, Incident
from noc.domain.incident_status import IncidentStatus
from noc.reporting import plain_language as words
from noc.store import remediation
from noc.store.decisions import EXECUTED_STATUSES, IN_FLIGHT_STATUSES

OPENED = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
NOW = datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
RESTART = "restart_service"


def incident(status: str = "INVESTIGATING", title: str = "CPU busy on alpha-1") -> Incident:
    return Incident(
        id=uuid.uuid4(),
        target_id=uuid.uuid4(),
        status=status,
        severity="warning",
        title=title,
        trace_id="a" * 32,
        opened_at=OPENED,
    )


def action(status: str, eligible: bool = True, expires_at: datetime | None = None) -> ActionRow:
    return ActionRow(
        action_type=RESTART,
        resource_id="svc:demo-shop",
        status=status,
        eligible=eligible,
        gate_failures=[],
        approval_expires_at=expires_at,
    )


def test_every_status_the_store_uses_has_an_explicit_verdict() -> None:
    store_statuses = {
        *remediation.CURRENT_STATUSES,
        remediation.PROPOSED,
        *IN_FLIGHT_STATUSES,
        *EXECUTED_STATUSES,
    }
    assert store_statuses <= VERDICT_BY_STATUS.keys()


@pytest.mark.parametrize(
    ("status", "eligible", "expected"),
    [
        ("proposed", True, "waiting"),
        ("pending_approval", True, "approval"),
        ("authorized", True, "running"),
        ("dispatched", True, "running"),
        ("executing", True, "running"),
        ("succeeded", True, "ran"),
        ("failed", True, "failed"),
        ("refused", True, "failed"),
        ("outcome_unknown", True, "unknown"),
        ("rejected", True, "rejected"),
        ("expired", True, "expired"),
        ("cancelled", True, "cancelled"),
        ("ineligible", False, "blocked"),
    ],
)
def test_each_action_status_has_its_plain_verdict(
    status: str, eligible: bool, expected: str
) -> None:
    assert action_verdict(action(status, eligible), NOW) == expected


def test_a_pending_approval_past_its_window_reads_as_expired() -> None:
    late = action("pending_approval", expires_at=datetime(2026, 10, 14, 9, 30, tzinfo=UTC))
    assert action_verdict(late, NOW) == "expired"


def test_a_proposed_action_does_not_claim_to_wait_for_approval() -> None:
    label = words.VERDICT_LABELS[action_verdict(action("proposed"), NOW)]
    assert label == "Not started yet"


def test_every_verdict_has_a_plain_label() -> None:
    verdicts = {*VERDICT_BY_STATUS.values(), "blocked"}
    assert all(verdict in words.VERDICT_LABELS for verdict in verdicts)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        ("succeeded", "Ran restart service."),
        ("failed", "Tried restart service, and it failed."),
        ("outcome_unknown", "Ran restart service, but the result is not known."),
        ("dispatched", "Running restart service."),
        ("rejected", "Nothing — a person rejected the planned action."),
        ("expired", "Nothing — nobody approved the planned action in time."),
        ("cancelled", "Nothing — the planned action was cancelled."),
    ],
)
def test_what_we_did_describes_each_outcome_in_plain_words(status: str, expected: str) -> None:
    assert did_text(incident(), [action(status)]) == expected


def test_a_waiting_action_says_nothing_ran_yet() -> None:
    assert did_text(incident(), [action("pending_approval")]) == "Nothing was run yet."


def test_the_headline_of_an_action_waiting_for_approval_asks_for_a_decision() -> None:
    waiting = incident("AWAITING_APPROVAL")
    headline = build_headline(
        waiting,
        IncidentStatus.AWAITING_APPROVAL,
        "Waiting for approval",
        action("pending_approval"),
    )
    assert headline == (
        "CPU busy on alpha-1 needs you: a planned action is waiting for your approval."
    )


def test_the_headline_says_when_the_approval_request_expired() -> None:
    waiting = incident("AWAITING_APPROVAL")
    headline = build_headline(
        waiting, IncidentStatus.AWAITING_APPROVAL, "Waiting for approval", None
    )
    assert headline == "CPU busy on alpha-1 needs you: the approval request expired."


def test_the_advice_for_an_action_waiting_for_approval_lists_the_steps() -> None:
    advice = build_advice(
        incident("AWAITING_APPROVAL"),
        IncidentStatus.AWAITING_APPROVAL,
        None,
        action("pending_approval"),
    )
    assert advice == StoryAdvice(
        text="Review the planned action below and approve or reject it.",
        steps=[
            "Check the gates and the impact score.",
            "Approve to let the NOC run it, or reject to handle it yourself.",
        ],
    )


def test_the_advice_without_an_open_request_says_to_decide_by_hand() -> None:
    advice = build_advice(
        incident("AWAITING_APPROVAL"), IncidentStatus.AWAITING_APPROVAL, None, None
    )
    assert advice.steps == []
    assert advice.text == words.APPROVAL_EXPIRED_TEXT
