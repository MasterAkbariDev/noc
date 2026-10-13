import pytest

from noc.domain.incident_status import (
    ALLOWED_TRANSITIONS,
    CLOSED_STATUSES,
    IncidentStatus,
    InvalidTransition,
    ensure_transition,
)


def test_every_status_has_a_transition_rule() -> None:
    assert set(ALLOWED_TRANSITIONS) == set(IncidentStatus)


def test_closed_is_terminal() -> None:
    assert ALLOWED_TRANSITIONS[IncidentStatus.CLOSED] == frozenset()


@pytest.mark.parametrize(
    ("current", "requested"),
    [
        (IncidentStatus.NEW, IncidentStatus.DIAGNOSED),
        (IncidentStatus.NEW, IncidentStatus.REMEDIATING),
        (IncidentStatus.DIAGNOSED, IncidentStatus.REMEDIATING),
        (IncidentStatus.ESCALATED, IncidentStatus.RESOLVED),
    ],
)
def test_skipping_steps_is_rejected(current: IncidentStatus, requested: IncidentStatus) -> None:
    with pytest.raises(InvalidTransition):
        ensure_transition(current, requested)


def test_remediation_needs_a_plan_first() -> None:
    reachable_remediating = {
        status
        for status, targets in ALLOWED_TRANSITIONS.items()
        if IncidentStatus.REMEDIATING in targets
    }
    assert reachable_remediating == {IncidentStatus.PLANNED, IncidentStatus.AWAITING_APPROVAL}


def test_escalated_incidents_stay_open() -> None:
    assert IncidentStatus.ESCALATED not in CLOSED_STATUSES
