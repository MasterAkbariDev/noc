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

export const EVENT_TYPE_LABELS = new Map<string, string>([
  ["incident_opened", "Incident opened"],
  ["alert_attached", "Alert added"],
  ["state_changed", "Status changed"],
  ["investigation_planned", "Investigation planned"],
  ["specialist_finished", "Specialist finished"],
  ["specialist_failed", "Specialist failed"],
  ["specialist_unavailable", "Specialist unavailable"],
  ["investigation_abandoned", "Investigation stopped"],
  ["report_generated", "Report written"],
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

