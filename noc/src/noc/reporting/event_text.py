from collections.abc import Callable, Mapping
from typing import Any, Final

from noc.reporting import plain_language as words

Payload = Mapping[str, Any]

ACTION_PHASES: Final = {
    "action_authorized": "approved to run",
    "action_dispatched": "started",
    "action_succeeded": "done, it worked",
    "action_failed": "failed",
    "action_outcome_unknown": "ran, but the result is not known",
    "action_cancelled": "cancelled",
}
DECISIONS: Final = {"approved": "approved", "rejected": "rejected"}


def resource_name(resource_id: object) -> str:
    text = str(resource_id or "")
    return text.split(":", 1)[1] if ":" in text else text


def action_phrase(payload: Payload) -> str:
    action = words.humanize(str(payload.get("action_type") or "an action"))
    resource = resource_name(payload.get("resource_id"))
    return f"{action} on {resource}" if resource else action


def plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def listed(names: list[str]) -> str:
    if len(names) <= 1:
        return "".join(names)
    return f"{', '.join(names[:-1])} and {names[-1]}"


def status_label(value: object) -> str:
    return words.text_for(words.STATUS_LABELS, str(value)) if value else "-"


def state_changed(actor: str, payload: Payload) -> str:
    text = f"Status: {status_label(payload.get('from'))} → {status_label(payload.get('to'))}"
    reason = payload.get("reason")
    if reason:
        why, _ = words.escalation_pair(str(reason))
        text += f", because {why}"
    return text


def specialist_finished(actor: str, payload: Payload) -> str:
    findings = int(payload.get("findings", 0))
    dropped = int(payload.get("dropped_findings", 0))
    text = f"The {actor} specialist finished with {plural(findings, 'finding')}"
    if dropped:
        text += (
            f"; {plural(dropped, 'more finding')} thrown away because the quote did not match "
            "what the server returned"
        )
    return text


def investigation_planned(actor: str, payload: Payload) -> str:
    names = [str(name) for name in payload.get("specialists", [])]
    if not names:
        return "The investigation was planned"
    return f"Sent the {listed(names)} {'specialist' if len(names) == 1 else 'specialists'} to look"


def approval_decided(actor: str, payload: Payload) -> str:
    decision = DECISIONS.get(str(payload.get("decision")), "decided on")
    text = f"{actor} {decision}: {action_phrase(payload)}"
    comment = payload.get("comment")
    return f"{text} ({comment})" if comment else text


def verification(actor: str, payload: Payload) -> str:
    checks = {
        "service_active": ("the service is running", "the service is not running"),
        "alerts_resolved": ("the alert has stopped", "the alert is still firing"),
    }
    parts = [good if payload[key] else bad for key, (good, bad) in checks.items() if key in payload]
    return f"Checked the fix: {listed(parts)}" if parts else "Checked the fix"


WRITERS: dict[str, Callable[[str, Payload], str]] = {
    "incident_opened": lambda actor, payload: (
        f"The alert “{payload.get('alertname', 'unknown')}” fired and opened this incident"
    ),
    "alert_attached": lambda actor, payload: (
        f"Another alert joined this incident: {payload.get('alertname', 'unknown')}"
    ),
    words.STATE_CHANGED_EVENT: state_changed,
    "investigation_planned": investigation_planned,
    "investigation_abandoned": lambda actor, payload: "The investigation was stopped",
    "specialist_unavailable": lambda actor, payload: (
        f"The {payload.get('specialist', 'requested')} specialist was not available"
    ),
    "specialist_finished": specialist_finished,
    "specialist_failed": lambda actor, payload: f"The {actor} specialist failed",
    "approval_requested": lambda actor, payload: (
        f"Asked a person to approve: {action_phrase(payload)}"
    ),
    "approval_decided": approval_decided,
    "approval_expired": lambda actor, payload: "Nobody approved the action in time",
    "verification_passed": verification,
    "verification_failed": verification,
    "report_generated": lambda actor, payload: "Wrote the incident report",
}


def event_text(event_type: str, actor: str, payload: Payload) -> str:
    if event_type in ACTION_PHASES:
        return f"{action_phrase(payload)}: {ACTION_PHASES[event_type]}"
    writer = WRITERS.get(event_type)
    return writer(actor, payload) if writer else words.humanize(event_type)
