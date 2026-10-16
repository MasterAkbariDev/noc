from collections.abc import Mapping

from noc.domain.incident_status import EscalationReason, IncidentStatus
from noc.domain.severity import Severity
from noc.policy.models import AutomationLevel, Gate
from noc_shared.taxonomy import RootCauseCode

ESCALATION_FALLBACK = (
    "the cause needs a person to look",
    "Look at the report, fix it by hand, then close the incident with a note.",
)
ROOT_CAUSE_FALLBACK_ADVICE = "Investigate by hand."
WORKING_TEXT = "Nothing yet — the agents are still working."
APPROVAL_WAIT_TEXT = "Review the planned action below and approve or reject it."
APPROVAL_WAIT_STEPS = [
    "Check the gates and the impact score.",
    "Approve to let the NOC run it, or reject to handle it yourself.",
]
APPROVAL_EXPIRED_TEXT = (
    "The approval window passed without a decision. Decide by hand what to do, then close "
    "the incident with a note."
)
FINISHED_TEXT = "Nothing. This incident is finished."

STATUS_LABELS: dict[IncidentStatus, str] = {
    IncidentStatus.NEW: "New",
    IncidentStatus.INVESTIGATING: "Investigating",
    IncidentStatus.DIAGNOSED: "Diagnosed",
    IncidentStatus.PLANNED: "Planning the fix",
    IncidentStatus.AWAITING_APPROVAL: "Waiting for approval",
    IncidentStatus.REMEDIATING: "Fixing",
    IncidentStatus.VERIFYING: "Checking the fix",
    IncidentStatus.RESOLVED: "Resolved",
    IncidentStatus.SELF_RESOLVED: "Resolved on its own",
    IncidentStatus.ESCALATED: "Needs you",
    IncidentStatus.CLOSED: "Closed",
}

STEP_LABELS: dict[str, str] = {
    "detected": "Alert received",
    "investigated": "Investigated",
    "diagnosed": "Diagnosed",
    "decided": "Decided what to do",
    "acted": "Action taken",
    "outcome": "Outcome",
}

ESCALATION_TEXT: dict[EscalationReason, tuple[str, str]] = {
    EscalationReason.UNKNOWN_ROOT_CAUSE: (
        "the agents could not find the cause",
        "Look at the evidence, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.LOW_CONFIDENCE: (
        "the agents are not confident enough in the cause",
        "Check the evidence yourself, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.SECURITY_INCIDENT: (
        "the evidence may point to an attack",
        "Review the security findings, contain the threat by hand, then close the incident "
        "with a note.",
    ),
    EscalationReason.NO_ALLOWED_ACTION: (
        "no automatic action is allowed for this problem",
        "Fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.ACTION_BLOCKED: (
        "the safety rules blocked the planned action",
        "Check why it was blocked, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.APPROVAL_REJECTED: (
        "the planned action was rejected",
        "Decide the next step, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.APPROVAL_EXPIRED: (
        "nobody approved the planned action in time",
        "Decide whether to act, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.ACTION_FAILED: (
        "the automatic action failed",
        "Check the target, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.NOT_RECOVERED: (
        "the service did not recover after the action",
        "Check the service, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.BUDGET_EXHAUSTED: (
        "the agents ran out of their investigation budget",
        "Investigate by hand, then close the incident with a note.",
    ),
    EscalationReason.LLM_UNAVAILABLE: (
        "the AI model could not be reached",
        "Investigate by hand or try again later, then close the incident with a note.",
    ),
    EscalationReason.TARGET_UNREACHABLE: (
        "the sentinel on the target could not be reached",
        "Check that the target and its sentinel are running, then close the incident with a note.",
    ),
    EscalationReason.AUTOMATION_PAUSED: (
        "automatic actions are paused for this target",
        "Decide whether to resume them, fix it by hand, then close the incident with a note.",
    ),
    EscalationReason.INVESTIGATION_FAILED: (
        "the investigation stopped before it finished",
        "Investigate by hand, then close the incident with a note.",
    ),
    EscalationReason.EXECUTION_NOT_AVAILABLE: (
        "automatic actions are switched off on this server",
        "Fix it by hand, then close the incident with a note.",
    ),
}

GATE_TEXT: dict[Gate, str] = {
    Gate.KILL_SWITCH: "the global kill switch is on",
    Gate.EXECUTION_DISABLED: "automatic actions are switched off on this server",
    Gate.UNKNOWN_ACTION: "the policy does not know this action",
    Gate.BLOCKED_ACTION: "the policy blocks this action",
    Gate.OBSERVE_ONLY: "this target only watches and does not act",
    Gate.NOT_ALLOWED_ON_RESOURCE: "this action is not allowed on this resource",
    Gate.UNREGISTERED_RESOURCE: "the resource is not registered with the sentinel",
    Gate.PROTECTED_RESOURCE: "the resource is protected",
    Gate.MISSING_SERVICE_PROFILE: "the service has no safety profile",
    Gate.STALE_EVIDENCE: "the evidence is too old to act on",
    Gate.ACTION_IN_FLIGHT: "another action is already running on this host",
    Gate.ATTEMPT_BUDGET: "this action has already been tried too often",
    Gate.MISSING_RECOVERY_ASSET: "there is no recovery plan for this action",
    Gate.NO_HEADROOM: "the host has no spare capacity for this action",
    Gate.CHANGE_IN_PROGRESS: "a planned change is in progress",
    Gate.SECURITY_NON_CONTAINMENT: "this would not contain the security problem",
    Gate.NO_EVIDENCE: "there is no evidence to support this action",
}

ROOT_CAUSE_TEXT: dict[RootCauseCode, tuple[str, str]] = {
    RootCauseCode.CPU_RUNAWAY_PROCESS: (
        "A process is using too much CPU",
        "Find the process and stop or fix it.",
    ),
    RootCauseCode.MEMORY_LEAK: (
        "Memory use keeps growing",
        "Restart the service and find the leak in its code.",
    ),
    RootCauseCode.OOM_KILL_LOOP: (
        "The service keeps running out of memory",
        "Give it more memory or fix the leak.",
    ),
    RootCauseCode.DISK_FULL_LOGS: (
        "Logs are filling the disk",
        "Free space and enable log rotation.",
    ),
    RootCauseCode.DISK_FULL_DATA: (
        "Data is filling the disk",
        "Free space or add more disk.",
    ),
    RootCauseCode.INODE_EXHAUSTION: (
        "The disk has run out of file entries",
        "Delete the many small files and find out what creates them.",
    ),
    RootCauseCode.SERVICE_CRASHED: (
        "The service crashed and did not restart",
        "Start the service and check why it stopped.",
    ),
    RootCauseCode.SERVICE_MISCONFIGURED: (
        "The service configuration is wrong",
        "Fix the configuration and restart the service.",
    ),
    RootCauseCode.BAD_DEPLOY: (
        "A recent release broke the service",
        "Roll the release back.",
    ),
    RootCauseCode.DEPENDENCY_DB_UNAVAILABLE: (
        "The database the service needs is unavailable",
        "Check the database and the network path to it.",
    ),
    RootCauseCode.DB_CONNECTION_EXHAUSTION: (
        "The database has no free connections",
        "Find the clients that hold connections and fix how they pool them.",
    ),
    RootCauseCode.UPSTREAM_LATENCY: (
        "A service this one depends on is slow",
        "Check the upstream service.",
    ),
    RootCauseCode.NETWORK_LATENCY: (
        "The network is slow",
        "Check the network path and how loaded it is.",
    ),
    RootCauseCode.NETWORK_PARTITION: (
        "Part of the network cannot be reached",
        "Check the network links and routing.",
    ),
    RootCauseCode.DNS_RESOLUTION_FAILURE: (
        "Names do not resolve",
        "Check the DNS servers and records.",
    ),
    RootCauseCode.TLS_CERTIFICATE_INVALID: (
        "A TLS certificate is invalid or has expired",
        "Renew or replace the certificate.",
    ),
    RootCauseCode.CLOCK_SKEW: (
        "The server clock is wrong",
        "Fix time synchronization on the server.",
    ),
    RootCauseCode.NOISY_NEIGHBOR: (
        "Another workload is using the shared resources",
        "Move or limit the other workload.",
    ),
    RootCauseCode.BRUTE_FORCE_SSH: (
        "Someone is trying to guess SSH passwords",
        "Block the source addresses and check that password login is off.",
    ),
    RootCauseCode.SUSPICIOUS_PROCESS: (
        "An unknown process is running",
        "Check the process and treat the host as possibly compromised.",
    ),
    RootCauseCode.TRANSIENT_SPIKE: (
        "A short spike that has passed",
        "Watch it. No change is needed unless it returns.",
    ),
    RootCauseCode.UNKNOWN: (
        "The cause is not known",
        ROOT_CAUSE_FALLBACK_ADVICE,
    ),
}

SEVERITY_LABELS: dict[Severity, str] = {
    Severity.INFO: "Info",
    Severity.WARNING: "Warning",
    Severity.CRITICAL: "Critical",
}

AUTOMATION_LABELS: dict[AutomationLevel, str] = {
    AutomationLevel.OBSERVE_ONLY: "Watch only",
    AutomationLevel.APPROVAL_REQUIRED: "Fixes need approval",
    AutomationLevel.AUTO_SAFE: "Safe fixes run automatically",
}

VERDICT_LABELS: dict[str, str] = {
    "approval": "Waiting for approval",
    "waiting": "Not started yet",
    "running": "Running",
    "ran": "Done",
    "failed": "Failed",
    "unknown": "Result unknown",
    "rejected": "Rejected by a person",
    "expired": "Approval expired",
    "cancelled": "Cancelled",
    "blocked": "Blocked",
}

STATE_CHANGED_EVENT = "state_changed"

ACTION_LABELS: dict[str, str] = {
    "wait_and_watch": "wait and watch",
    "start_service": "start the service",
    "restart_service": "restart the service",
    "restart_container": "restart the container",
    "stop_service": "stop the service",
    "throttle_cpu": "limit the CPU use",
    "limit_memory": "limit the memory use",
    "vacuum_journal": "shrink the system log",
    "rotate_logs": "compress the big log files",
    "clean_temp_dir": "delete old temporary files",
    "docker_prune_dangling": "remove unused Docker images",
    "kill_process": "kill the process",
    "block_ip": "block the address",
    "rollback_release": "go back to the previous version",
    "reboot_host": "restart the whole server",
}

EVENT_SENTENCES: dict[str, str] = {
    "incident_opened": "{title} was opened",
    "alert_attached": "An alert was added to {title}",
    "report_generated": "A report was written for {title}",
    "investigation_planned": "The investigation of {title} was planned",
    "investigation_abandoned": "The investigation of {title} was abandoned",
    "specialist_unavailable": "A specialist was unavailable for {title}",
    "specialist_finished": "{actor} finished checking {title}",
    "specialist_failed": "{actor} failed while checking {title}",
    "action_authorized": "An action for {title} was approved to run",
    "approval_requested": "An action for {title} is waiting for an approval",
    "approval_decided": "{actor} recorded a decision on an action for {title}",
    "approval_expired": "Nobody approved an action for {title} in time",
    "action_dispatched": "An action for {title} started",
    "action_succeeded": "An action for {title} succeeded",
    "action_failed": "An action for {title} failed",
    "action_outcome_unknown": "The result of an action for {title} is unknown",
    "action_cancelled": "An action for {title} was cancelled",
    "verification_passed": "The check after the fix for {title} passed",
    "verification_failed": "The check after the fix for {title} failed",
    "next_action_planned": "The first fix for {title} was not enough, so the NOC tries another",
}

AUDIT_ACTION_LABELS: dict[str, str] = {
    "user_created": "User created",
    "user_disabled": "User disabled",
    "user_enabled": "User enabled",
    "user_role_changed": "Role changed",
    "user_password_reset": "Password reset by an admin",
    "password_changed": "Password changed",
    "login": "Signed in",
    "logout": "Signed out",
    "login_failed": "Failed sign-in",
    "incident_closed": "Incident closed",
    "target_added": "Target added",
    "target_automation_set": "Automation level changed",
    "target_auto_actions_set": "Automatic actions changed",
    "target_profile_set": "Service profile changed",
    "scenario_run_started": "Chaos scenario started",
    "scenario_run_finished": "Chaos scenario finished",
}


def humanize(code: str) -> str:
    sentence = code.replace("_", " ").strip()
    return sentence[:1].upper() + sentence[1:]


def action_label(action_type: str) -> str:
    return ACTION_LABELS.get(action_type) or action_type.replace("_", " ").strip()


def action_title(action_type: str) -> str:
    label = action_label(action_type)
    return label[:1].upper() + label[1:]


def lookup[K: str, T](table: Mapping[K, T], value: str) -> T | None:
    for key, item in table.items():
        if key == value:
            return item
    return None


def text_for[K: str](table: Mapping[K, str], value: str) -> str:
    return lookup(table, value) or humanize(value)


def escalation_pair(value: str | None) -> tuple[str, str]:
    if value is None:
        return ESCALATION_FALLBACK
    return lookup(ESCALATION_TEXT, value) or (humanize(value), ESCALATION_FALLBACK[1])


def root_cause_pair(value: str) -> tuple[str, str]:
    return lookup(ROOT_CAUSE_TEXT, value) or (humanize(value), ROOT_CAUSE_FALLBACK_ADVICE)
