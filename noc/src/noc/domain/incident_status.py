from enum import StrEnum


class IncidentStatus(StrEnum):
    NEW = "NEW"
    INVESTIGATING = "INVESTIGATING"
    DIAGNOSED = "DIAGNOSED"
    PLANNED = "PLANNED"
    AWAITING_APPROVAL = "AWAITING_APPROVAL"
    REMEDIATING = "REMEDIATING"
    VERIFYING = "VERIFYING"
    RESOLVED = "RESOLVED"
    SELF_RESOLVED = "SELF_RESOLVED"
    ESCALATED = "ESCALATED"
    CLOSED = "CLOSED"


S = IncidentStatus

ALLOWED_TRANSITIONS: dict[IncidentStatus, frozenset[IncidentStatus]] = {
    S.NEW: frozenset({S.INVESTIGATING}),
    S.INVESTIGATING: frozenset({S.DIAGNOSED, S.SELF_RESOLVED, S.ESCALATED}),
    S.DIAGNOSED: frozenset({S.INVESTIGATING, S.PLANNED, S.ESCALATED}),
    S.PLANNED: frozenset({S.AWAITING_APPROVAL, S.REMEDIATING, S.ESCALATED}),
    S.AWAITING_APPROVAL: frozenset({S.REMEDIATING, S.ESCALATED}),
    S.REMEDIATING: frozenset({S.VERIFYING, S.ESCALATED}),
    S.VERIFYING: frozenset({S.RESOLVED, S.DIAGNOSED, S.ESCALATED}),
    S.RESOLVED: frozenset({S.CLOSED}),
    S.SELF_RESOLVED: frozenset({S.CLOSED}),
    S.ESCALATED: frozenset({S.CLOSED}),
    S.CLOSED: frozenset(),
}

CLOSED_STATUSES = frozenset({S.RESOLVED, S.SELF_RESOLVED, S.CLOSED})
OPEN_STATUSES = frozenset(IncidentStatus) - CLOSED_STATUSES
ACTIVE_STATUSES = OPEN_STATUSES - {S.ESCALATED}

TIMESTAMP_FIELD: dict[IncidentStatus, str] = {
    S.INVESTIGATING: "investigation_started_at",
    S.DIAGNOSED: "diagnosed_at",
    S.PLANNED: "plan_at",
    S.ESCALATED: "escalated_at",
    S.RESOLVED: "resolved_at",
    S.SELF_RESOLVED: "resolved_at",
    S.CLOSED: "closed_at",
}


class EscalationReason(StrEnum):
    UNKNOWN_ROOT_CAUSE = "unknown_root_cause"
    LOW_CONFIDENCE = "low_confidence"
    SECURITY_INCIDENT = "security_incident"
    NO_ALLOWED_ACTION = "no_allowed_action"
    ACTION_BLOCKED = "action_blocked"
    APPROVAL_REJECTED = "approval_rejected"
    APPROVAL_EXPIRED = "approval_expired"
    ACTION_FAILED = "action_failed"
    NOT_RECOVERED = "not_recovered"
    BUDGET_EXHAUSTED = "budget_exhausted"
    LLM_UNAVAILABLE = "llm_unavailable"
    TARGET_UNREACHABLE = "target_unreachable"
    AUTOMATION_PAUSED = "automation_paused"
    INVESTIGATION_FAILED = "investigation_failed"
    EXECUTION_NOT_AVAILABLE = "execution_not_available"


class InvalidTransition(Exception):
    def __init__(self, current: IncidentStatus, requested: IncidentStatus) -> None:
        super().__init__(f"{current} -> {requested} is not allowed")
        self.current = current
        self.requested = requested


def ensure_transition(current: IncidentStatus, requested: IncidentStatus) -> None:
    if requested not in ALLOWED_TRANSITIONS[current]:
        raise InvalidTransition(current, requested)
