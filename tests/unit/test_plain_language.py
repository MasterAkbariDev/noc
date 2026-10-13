from collections.abc import Mapping
from enum import StrEnum

import pytest

from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.domain.severity import Severity
from noc.policy.models import AutomationLevel, Gate
from noc.reporting.plain_language import (
    AUDIT_ACTION_LABELS,
    AUTOMATION_LABELS,
    ESCALATION_FALLBACK,
    ESCALATION_TEXT,
    GATE_TEXT,
    ROOT_CAUSE_TEXT,
    SEVERITY_LABELS,
    STATUS_LABELS,
    escalation_pair,
    humanize,
    root_cause_pair,
    text_for,
)
from noc_shared.taxonomy import RootCauseCode


@pytest.mark.parametrize(
    ("table", "enum_type"),
    [
        (STATUS_LABELS, IncidentStatus),
        (ESCALATION_TEXT, EscalationReason),
        (GATE_TEXT, Gate),
        (ROOT_CAUSE_TEXT, RootCauseCode),
        (SEVERITY_LABELS, Severity),
        (AUTOMATION_LABELS, AutomationLevel),
    ],
)
def test_every_enum_member_has_wording(
    table: Mapping[object, object], enum_type: type[StrEnum]
) -> None:
    assert set(table) == set(enum_type)


def test_every_audit_action_in_the_contract_has_a_label() -> None:
    contract_actions = {
        "user_created",
        "user_disabled",
        "user_enabled",
        "user_role_changed",
        "user_password_reset",
        "password_changed",
        "login",
        "logout",
        "login_failed",
        "incident_closed",
    }
    assert contract_actions <= set(AUDIT_ACTION_LABELS)


@pytest.mark.parametrize(
    "label",
    [
        *STATUS_LABELS.values(),
        *SEVERITY_LABELS.values(),
        *AUTOMATION_LABELS.values(),
        *AUDIT_ACTION_LABELS.values(),
        *(why for why, _ in ESCALATION_TEXT.values()),
        *(label for label, _ in ROOT_CAUSE_TEXT.values()),
        *GATE_TEXT.values(),
    ],
)
def test_wording_is_plain_text_without_code_names(label: str) -> None:
    assert label
    assert "_" not in label
    assert label == label.strip()


@pytest.mark.parametrize(
    "text",
    [
        *(label for label, _ in ROOT_CAUSE_TEXT.values()),
        *(advice for _, advice in ESCALATION_TEXT.values()),
        *(advice for _, advice in ROOT_CAUSE_TEXT.values()),
        *STATUS_LABELS.values(),
        *SEVERITY_LABELS.values(),
        *AUTOMATION_LABELS.values(),
    ],
)
def test_wording_starts_with_a_capital_letter(text: str) -> None:
    assert text[0].isupper()


def test_humanize_turns_a_code_into_a_sentence() -> None:
    assert humanize("no_headroom") == "No headroom"
    assert humanize("ServiceDown") == "ServiceDown"


def test_unknown_code_falls_back_to_humanized_text() -> None:
    assert text_for(GATE_TEXT, "brand_new_gate") == "Brand new gate"


def test_escalation_pair_uses_the_operator_wording() -> None:
    why, what_to_do = escalation_pair(EscalationReason.EXECUTION_NOT_AVAILABLE.value)
    assert why == "automatic actions are switched off on this server"
    assert what_to_do == "Fix it by hand, then close the incident with a note."


def test_escalation_pair_without_a_reason_uses_the_fallback() -> None:
    assert escalation_pair(None) == ESCALATION_FALLBACK


def test_root_cause_pair_uses_label_and_advice() -> None:
    assert root_cause_pair(RootCauseCode.DISK_FULL_LOGS.value) == (
        "Logs are filling the disk",
        "Free space and enable log rotation.",
    )


def test_unknown_root_cause_is_still_described() -> None:
    label, advice = root_cause_pair("quantum_weather")
    assert label == "Quantum weather"
    assert advice == "Investigate by hand."
