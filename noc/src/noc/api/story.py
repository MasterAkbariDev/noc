import uuid
from collections.abc import Collection
from datetime import UTC, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_role
from noc.api.schemas import (
    IncidentStory,
    StepState,
    StoryAction,
    StoryAdvice,
    StoryDid,
    StoryFound,
    StoryPoint,
    StoryStep,
    StoryText,
)
from noc.auth.roles import Role
from noc.db.models import ActionRow, AlertEvent, DiagnosisRow, FindingRow, Incident, Target
from noc.domain.incident_status import ACTIVE_STATUSES, CLOSED_STATUSES, IncidentStatus
from noc.reporting import plain_language as words
from noc.store.decisions import EXECUTED_STATUSES, IN_FLIGHT_STATUSES
from noc.store.remediation import (
    AUTHORIZED,
    CANCELLED,
    DISPATCHED,
    EXPIRED,
    FAILED,
    OUTCOME_UNKNOWN,
    PENDING_APPROVAL,
    PROPOSED,
    REFUSED,
    REJECTED,
    SUCCEEDED,
)
from noc_shared.taxonomy import RootCauseCode

router = APIRouter(
    prefix="/api/incidents", tags=["story"], dependencies=[Depends(require_role(Role.VIEWER))]
)

Session = Annotated[AsyncSession, Depends(get_session)]
Step = tuple[str, StepState, datetime | None]
OUTCOME_KEY = "outcome"
FAILED_ACTION = "failed"
EXECUTING = "executing"
MAX_POINTS = 4
VERDICT_BY_STATUS: dict[str, str] = {
    PROPOSED: "waiting",
    PENDING_APPROVAL: "waiting",
    AUTHORIZED: "running",
    DISPATCHED: "running",
    EXECUTING: "running",
    SUCCEEDED: "ran",
    FAILED: "failed",
    REFUSED: "failed",
    OUTCOME_UNKNOWN: "unknown",
    REJECTED: "rejected",
    EXPIRED: "expired",
    CANCELLED: "cancelled",
}
DID_BY_STATUS: tuple[tuple[tuple[str, ...], str], ...] = (
    ((SUCCEEDED,), "Ran {names}."),
    ((FAILED, REFUSED), "Tried {names}, and it failed."),
    ((OUTCOME_UNKNOWN,), "Ran {names}, but the result is not known."),
    ((AUTHORIZED, DISPATCHED, EXECUTING), "Running {names}."),
    ((REJECTED,), "Nothing — a person rejected the planned action."),
    ((EXPIRED,), "Nothing — nobody approved the planned action in time."),
    ((CANCELLED,), "Nothing — the planned action was cancelled."),
)


@router.get("/{incident_id}/story")
async def get_incident_story(incident_id: uuid.UUID, session: Session) -> IncidentStory:
    incident = await session.get(Incident, incident_id)
    if incident is None:
        raise HTTPException(404, "incident not found")
    target = await session.get_one(Target, incident.target_id)
    alert = await session.scalar(
        select(AlertEvent)
        .where(AlertEvent.incident_id == incident_id)
        .order_by(AlertEvent.starts_at)
        .limit(1)
    )
    findings = await session.scalars(
        select(FindingRow).where(FindingRow.incident_id == incident_id).order_by(FindingRow.label)
    )
    diagnosis = await session.scalar(
        select(DiagnosisRow)
        .where(DiagnosisRow.incident_id == incident_id)
        .order_by(DiagnosisRow.created_at.desc())
        .limit(1)
    )
    actions = await session.scalars(
        select(ActionRow).where(ActionRow.incident_id == incident_id).order_by(ActionRow.created_at)
    )
    return build_story(incident, target.name, alert, list(findings), diagnosis, list(actions))


def build_story(
    incident: Incident,
    target_name: str,
    alert: AlertEvent | None,
    findings: list[FindingRow],
    diagnosis: DiagnosisRow | None,
    actions: list[ActionRow],
) -> IncidentStory:
    status = IncidentStatus(incident.status)
    status_label = words.text_for(words.STATUS_LABELS, incident.status)
    code = root_cause_code(incident, diagnosis)
    return IncidentStory(
        id=incident.id,
        title=incident.title,
        target=target_name,
        severity=incident.severity,
        status=incident.status,
        status_label=status_label,
        headline=build_headline(incident, status, status_label),
        steps=build_steps(incident, status, actions),
        what_happened=build_what_happened(incident, alert),
        what_we_found=build_found(incident, diagnosis, findings),
        what_we_did=build_did(incident, actions),
        what_you_should_do=build_advice(incident, status, code, pending_action(actions)),
    )


def build_headline(incident: Incident, status: IncidentStatus, status_label: str) -> str:
    if status is IncidentStatus.ESCALATED:
        why, _ = words.escalation_pair(incident.escalation_reason)
        return f"{incident.title} needs you: {why}."
    if status is IncidentStatus.AWAITING_APPROVAL:
        return f"{incident.title} needs you: a planned action is waiting for your approval."
    return f"{incident.title}: {status_label.lower()}."


def pending_action(actions: list[ActionRow]) -> ActionRow | None:
    return next((action for action in actions if action.status == PENDING_APPROVAL), None)


def build_steps(
    incident: Incident, status: IncidentStatus, actions: list[ActionRow]
) -> list[StoryStep]:
    rows: list[Step] = [
        ("detected", "done", incident.opened_at),
        ("investigated", *investigated_state(incident, status)),
        ("diagnosed", *diagnosed_state(incident, status)),
        ("decided", *decided_state(incident, status, actions)),
        ("acted", *acted_state(status, actions)),
        (OUTCOME_KEY, *outcome_state(incident, status)),
    ]
    if status in ACTIVE_STATUSES:
        rows = mark_first_pending_current(rows)
    return [
        StoryStep(key=key, label=step_title(key, status), state=state, at=at)
        for key, state, at in rows
    ]


def mark_first_pending_current(rows: list[Step]) -> list[Step]:
    for index, (key, state, at) in enumerate(rows):
        if state == "pending":
            return [*rows[:index], (key, "current", at), *rows[index + 1 :]]
    return rows


def step_title(key: str, status: IncidentStatus) -> str:
    if key == OUTCOME_KEY and (status is IncidentStatus.ESCALATED or status in CLOSED_STATUSES):
        return words.text_for(words.STATUS_LABELS, status.value)
    return words.text_for(words.STEP_LABELS, key)


def unfinished_state(status: IncidentStatus) -> StepState:
    return "pending" if status in ACTIVE_STATUSES else "skipped"


def investigated_state(
    incident: Incident, status: IncidentStatus
) -> tuple[StepState, datetime | None]:
    started = incident.investigation_started_at
    if incident.diagnosed_at is not None:
        return "done", started
    if status in ACTIVE_STATUSES:
        return "pending", started
    if incident.escalated_at is not None:
        return "failed", started
    return "done", started


def diagnosed_state(
    incident: Incident, status: IncidentStatus
) -> tuple[StepState, datetime | None]:
    if incident.diagnosed_at is not None:
        return "done", incident.diagnosed_at
    return unfinished_state(status), None


def decided_state(
    incident: Incident, status: IncidentStatus, actions: list[ActionRow]
) -> tuple[StepState, datetime | None]:
    if incident.plan_at is not None or actions:
        return "done", incident.plan_at
    return unfinished_state(status), None


def acted_state(
    status: IncidentStatus, actions: list[ActionRow]
) -> tuple[StepState, datetime | None]:
    if has_action_status(actions, (FAILED_ACTION,)):
        return "failed", None
    if has_action_status(actions, IN_FLIGHT_STATUSES):
        return ("current" if status in ACTIVE_STATUSES else "done"), None
    if has_action_status(actions, EXECUTED_STATUSES):
        return "done", None
    return unfinished_state(status), None


def has_action_status(actions: list[ActionRow], statuses: Collection[str]) -> bool:
    return any(action.status in statuses for action in actions)


def outcome_state(incident: Incident, status: IncidentStatus) -> tuple[StepState, datetime | None]:
    if status is IncidentStatus.ESCALATED:
        return "current", incident.escalated_at
    if status is IncidentStatus.CLOSED:
        return "done", incident.closed_at
    if status in CLOSED_STATUSES:
        return "done", incident.resolved_at
    return "pending", None


def build_what_happened(incident: Incident, alert: AlertEvent | None) -> StoryText:
    if alert is None:
        return StoryText(
            text=f"{incident.title}. Opened at {clock(incident.opened_at)} UTC.",
            technical=None,
        )
    summary = (
        alert.annotations.get("summary")
        or alert.annotations.get("description")
        or words.humanize(alert.alertname)
    )
    labels = [f"alertname={alert.alertname}"] + [
        f"{key}={value}" for key, value in sorted(alert.labels.items()) if key != "alertname"
    ]
    return StoryText(
        text=f"{summary.rstrip('.')} at {clock(alert.starts_at)} UTC.",
        technical=", ".join(labels),
    )


def clock(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%H:%M")


def root_cause_code(incident: Incident, diagnosis: DiagnosisRow | None) -> str | None:
    if diagnosis is not None:
        return diagnosis.primary_code
    return incident.root_cause_code


def build_found(
    incident: Incident, diagnosis: DiagnosisRow | None, findings: list[FindingRow]
) -> StoryFound:
    code = root_cause_code(incident, diagnosis)
    confidence = diagnosis.confidence if diagnosis is not None else incident.confidence
    supporters = supporting_labels(diagnosis)
    ranked = sorted(findings, key=lambda finding: point_rank(finding, finding.label in supporters))
    return StoryFound(
        text=found_text(code, confidence),
        root_cause_code=code,
        root_cause_label=words.root_cause_pair(code)[0] if code is not None else None,
        confidence=confidence,
        points=[story_point(finding) for finding in ranked[:MAX_POINTS]],
    )


def supporting_labels(diagnosis: DiagnosisRow | None) -> set[str]:
    if diagnosis is None:
        return set()
    primary = [
        hypothesis
        for hypothesis in diagnosis.hypotheses
        if hypothesis.get("root_cause_code") == diagnosis.primary_code
    ]
    if not primary:
        return set()
    return {str(label) for label in primary[0].get("supporting_findings", [])}


def point_rank(finding: FindingRow, supports_primary: bool) -> tuple[bool, bool, float]:
    return (
        not (finding.grounded and supports_primary),
        not finding.grounded,
        -finding.confidence,
    )


def found_text(code: str | None, confidence: float | None) -> str:
    if code is None:
        return "Not diagnosed yet."
    if code == RootCauseCode.UNKNOWN.value:
        return "The agents could not find a cause."
    label, _ = words.root_cause_pair(code)
    if confidence is None:
        return f"Root cause: {label}."
    return f"Root cause: {label} ({round(confidence * 100)}% confidence)."


def story_point(finding: FindingRow) -> StoryPoint:
    return StoryPoint(
        text=finding.summary,
        agent=finding.agent,
        label=finding.label,
        refs=evidence_refs(finding.evidence),
        grounded=finding.grounded,
    )


def evidence_refs(evidence: list[dict[str, Any]]) -> list[str]:
    return [str(item["tool_call_ref"]) for item in evidence if "tool_call_ref" in item]


def build_did(incident: Incident, actions: list[ActionRow]) -> StoryDid:
    return StoryDid(
        text=did_text(incident, actions),
        considered=[story_action(action) for action in actions],
    )


def did_text(incident: Incident, actions: list[ActionRow]) -> str:
    for statuses, template in DID_BY_STATUS:
        named = [action for action in actions if action.status in statuses]
        if named:
            return template.format(names=action_names(named))
    gates = [gate for action in actions for gate in action.gate_failures]
    if gates:
        return f"Nothing — {words.text_for(words.GATE_TEXT, gates[0])}."
    if incident.escalation_reason is not None:
        why, _ = words.escalation_pair(incident.escalation_reason)
        return f"Nothing — {why}."
    if not actions:
        return "No action was proposed."
    return "Nothing was run yet."


def action_names(actions: list[ActionRow]) -> str:
    return ", ".join(words.humanize(action.action_type).lower() for action in actions)


def story_action(action: ActionRow) -> StoryAction:
    verdict = action_verdict(action)
    return StoryAction(
        action=action.action_type,
        action_label=words.humanize(action.action_type),
        verdict=verdict,
        verdict_label=words.text_for(words.VERDICT_LABELS, verdict),
        reasons=[words.text_for(words.GATE_TEXT, gate) for gate in action.gate_failures],
        technical=list(action.gate_failures),
    )


def action_verdict(action: ActionRow) -> str:
    verdict = VERDICT_BY_STATUS.get(action.status)
    if verdict is not None:
        return verdict
    if not action.eligible:
        return "blocked"
    return "waiting"


def build_advice(
    incident: Incident, status: IncidentStatus, code: str | None, pending: ActionRow | None
) -> StoryAdvice:
    if status is IncidentStatus.ESCALATED:
        _, what_to_do = words.escalation_pair(incident.escalation_reason)
        return StoryAdvice(text=what_to_do, steps=root_cause_steps(code))
    if status is IncidentStatus.AWAITING_APPROVAL:
        steps = list(words.APPROVAL_WAIT_STEPS) if pending is not None else []
        return StoryAdvice(text=words.APPROVAL_WAIT_TEXT, steps=steps)
    if status in ACTIVE_STATUSES:
        return StoryAdvice(text=words.WORKING_TEXT, steps=[])
    return StoryAdvice(text=words.FINISHED_TEXT, steps=[])


def root_cause_steps(code: str | None) -> list[str]:
    if code is None:
        return []
    _, advice = words.root_cause_pair(code)
    return [advice]
