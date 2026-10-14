import type { Tone } from "../../lib/tones";

const ACTION_STATUS_LABELS = new Map<string, string>([
  ["proposed", "Proposed"],
  ["ineligible", "Not allowed"],
  ["pending_approval", "Waiting for approval"],
  ["authorized", "Approved"],
  ["dispatched", "Running"],
  ["executing", "Running"],
  ["succeeded", "Succeeded"],
  ["failed", "Failed"],
  ["refused", "Refused"],
  ["outcome_unknown", "Outcome unknown"],
  ["cancelled", "Cancelled"],
  ["rejected", "Rejected"],
  ["expired", "Expired"],
]);

const EVENT_TYPE_LABELS = new Map<string, string>([
  ["approval_requested", "Approval requested"],
  ["approval_required", "Approval required"],
  ["approval_claim", "Approval claimed"],
  ["approval_decided", "Decision recorded"],
  ["approval_rejected", "Action rejected"],
  ["approval_expired", "Approval expired"],
  ["action_authorized", "Action approved"],
  ["action_blocked", "Action blocked"],
  ["action_dispatched", "Action started"],
  ["action_in_flight", "Another action is running"],
  ["action_succeeded", "Action succeeded"],
  ["action_failed", "Action failed"],
  ["action_outcome_unknown", "Action outcome unknown"],
  ["action_cancelled", "Action cancelled"],
  ["verification_passed", "Check after the fix passed"],
  ["verification_failed", "Check after the fix failed"],
]);

const RUN_STATUS_TONES = new Map<string, Tone>([
  ["succeeded", "ok"],
  ["failed", "critical"],
  ["running", "info"],
]);

const VERDICT_TONES = new Map<string, Tone>([
  ["ran", "ok"],
  ["failed", "critical"],
  ["blocked", "warning"],
  ["waiting", "info"],
]);

function humanize(code: string): string {
  const text = code.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function plainLabel(code: string): string {
  return humanize(code);
}

export function actionStatusLabel(status: string): string {
  return ACTION_STATUS_LABELS.get(status) ?? humanize(status);
}

export function eventTypeLabel(type: string): string {
  return EVENT_TYPE_LABELS.get(type) ?? humanize(type);
}

export function runStatusTone(status: string): Tone {
  return RUN_STATUS_TONES.get(status) ?? "neutral";
}

export function verdictTone(verdict: string): Tone {
  return VERDICT_TONES.get(verdict) ?? "neutral";
}
