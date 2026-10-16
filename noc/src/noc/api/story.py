import uuid
from collections.abc import Collection, Mapping
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from noc.api.deps import get_session, require_role
from noc.api.incidents import tool_sources
from noc.api.schemas import (
    IncidentStory,
    StepState,
    StoryAction,
    StoryAdvice,
    StoryDid,
    StoryEvidence,
    StoryFound,
    StoryPoint,
    StoryStep,
    StoryText,
)
from noc.auth.roles import Role
from noc.db.base import utc_now
from noc.db.models import (
    ActionRow,
    AlertEvent,
    DiagnosisRow,
    FindingRow,
    Incident,
    ManagedResourceRow,
    Target,
)
from noc.domain.incident_status import ACTIVE_STATUSES, CLOSED_STATUSES, IncidentStatus
from noc.reporting import plain_language as words
from noc.reporting.event_text import resource_name
from noc.reporting.operator_guide import (
    GuideContext,
    GuideStep,
    load_guide,
    steps_after_fix,
    steps_to_fix,
)
from noc.reporting.tool_text import evidence_with_sources
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
    PENDING_APPROVAL: "approval",
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
HEADLINE_ENDINGS: dict[IncidentStatus, str] = {
    IncidentStatus.RESOLVED: "the NOC fixed it and the check afterwards passed.",
    IncidentStatus.SELF_RESOLVED: "the problem went away on its own.",
    IncidentStatus.CLOSED: "closed.",
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
    context = await guide_context(session, incident, alert, diagnosis)
    sources = await tool_sources(session, incident_id)
    return build_story(
        incident, target.name, alert, list(findings), diagnosis, list(actions), context, sources
    )


def affected_resource_id(alert: AlertEvent | None, diagnosis: DiagnosisRow | None) -> str | None:
    if diagnosis is not None and diagnosis.hypotheses:
        primary = max(diagnosis.hypotheses, key=lambda item: float(item.get("confidence", 0)))
        if primary.get("affected_resource_id"):
            return str(primary["affected_resource_id"])
    if alert is not None:
        return alert.labels.get("resource")
    return None


async def guide_context(
    session: AsyncSession,
    incident: Incident,
    alert: AlertEvent | None,
    diagnosis: DiagnosisRow | None,
) -> GuideContext:
    resource_id = affected_resource_id(alert, diagnosis)
    resource = (
        await session.get(ManagedResourceRow, (incident.target_id, resource_id))
        if resource_id
        else None
    )
    unit = resource.name if resource is not None and resource.kind == "systemd_unit" else None
    mount = alert.labels.get("mountpoint") if alert is not None else None
    return GuideContext(unit=unit, mount=mount)


def build_story(
    incident: Incident,
    target_name: str,
    alert: AlertEvent | None,
    findings: list[FindingRow],
    diagnosis: DiagnosisRow | None,
    actions: list[ActionRow],
    context: GuideContext | None = None,
    sources: Mapping[str, str] | None = None,
) -> IncidentStory:
    status = IncidentStatus(incident.status)
    status_label = words.text_for(words.STATUS_LABELS, incident.status)
    code = root_cause_code(incident, diagnosis)
    now = utc_now()
    pending = pending_action(actions, now)
    return IncidentStory(
        id=incident.id,
        title=incident.title,
        target=target_name,
        severity=incident.severity,
        status=incident.status,
        status_label=status_label,
        headline=build_headline(incident, status, status_label, pending),
        steps=build_steps(incident, status, actions),
        what_happened=build_what_happened(incident, alert),
        what_we_found=build_found(incident, diagnosis, findings, sources or {}),
        what_we_did=build_did(incident, actions, now),
        what_you_should_do=build_advice(
            incident,
            status,
            code,
            pending,
            alert.alertname if alert is not None else None,
            context or GuideContext(),
        ),
    )


def build_headline(
    incident: Incident, status: IncidentStatus, status_label: str, pending: ActionRow | None
) -> str:
    if status is IncidentStatus.ESCALATED:
        why, _ = words.escalation_pair(incident.escalation_reason)
        return f"{incident.title} needs you: {why}."
    if status is IncidentStatus.AWAITING_APPROVAL and pending is None:
        return f"{incident.title} needs you: the approval request expired."
    if status is IncidentStatus.AWAITING_APPROVAL:
        return f"{incident.title} needs you: a planned action is waiting for your approval."
    ending = HEADLINE_ENDINGS.get(status)
    if ending is not None:
        return f"{incident.title}: {ending}"
    return f"{incident.title}: {status_label.lower()}. The NOC is working on it."


def approval_open(action: ActionRow, now: datetime) -> bool:
    expires_at = action.approval_expires_at
    return action.status == PENDING_APPROVAL and (expires_at is None or expires_at > now)


def pending_action(actions: list[ActionRow], now: datetime) -> ActionRow | None:
    return next((action for action in actions if approval_open(action, now)), None)


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
    incident: Incident,
    diagnosis: DiagnosisRow | None,
    findings: list[FindingRow],
    sources: Mapping[str, str],
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
        points=[story_point(finding, sources) for finding in ranked[:MAX_POINTS]],
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


def story_point(finding: FindingRow, sources: Mapping[str, str]) -> StoryPoint:
    return StoryPoint(
        text=finding.summary,
        agent=finding.agent,
        label=finding.label,
        evidence=[
            StoryEvidence(source=item["source"], quote=str(item.get("excerpt", "")))
            for item in evidence_with_sources(finding.evidence, sources)
        ],
        grounded=finding.grounded,
    )


def build_did(incident: Incident, actions: list[ActionRow], now: datetime) -> StoryDid:
    return StoryDid(
        text=did_text(incident, actions),
        considered=[story_action(action, now) for action in actions],
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


def story_action(action: ActionRow, now: datetime) -> StoryAction:
    verdict = action_verdict(action, now)
    return StoryAction(
        action=action.action_type,
        action_label=words.action_title(action.action_type)
        + f" on {resource_name(action.resource_id)}",
        verdict=verdict,
        verdict_label=words.text_for(words.VERDICT_LABELS, verdict),
        reasons=[words.text_for(words.GATE_TEXT, gate) for gate in action.gate_failures],
        technical=list(action.gate_failures),
    )


def action_verdict(action: ActionRow, now: datetime) -> str:
    if action.status == PENDING_APPROVAL and not approval_open(action, now):
        return "expired"
    verdict = VERDICT_BY_STATUS.get(action.status)
    if verdict is not None:
        return verdict
    if not action.eligible:
        return "blocked"
    return "waiting"


def build_advice(
    incident: Incident,
    status: IncidentStatus,
    code: str | None,
    pending: ActionRow | None,
    alertname: str | None = None,
    context: GuideContext | None = None,
) -> StoryAdvice:
    guide = load_guide()
    where = context or GuideContext()
    if status is IncidentStatus.ESCALATED:
        _, what_to_do = words.escalation_pair(incident.escalation_reason)
        return StoryAdvice(text=what_to_do, steps=steps_to_fix(guide, code, alertname, where))
    if status is IncidentStatus.AWAITING_APPROVAL and pending is None:
        return StoryAdvice(
            text=words.APPROVAL_EXPIRED_TEXT, steps=steps_to_fix(guide, code, alertname, where)
        )
    if status is IncidentStatus.AWAITING_APPROVAL:
        return StoryAdvice(
            text=words.APPROVAL_WAIT_TEXT,
            steps=[GuideStep(text=step) for step in words.APPROVAL_WAIT_STEPS],
        )
    if status in ACTIVE_STATUSES:
        return StoryAdvice(text=words.WORKING_TEXT, steps=[])
    return StoryAdvice(text=words.FINISHED_TEXT, steps=steps_after_fix(guide, code, where))
