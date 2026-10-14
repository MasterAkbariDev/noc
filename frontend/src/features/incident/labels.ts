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

export function actionStatusLabel(status: string): string {
  return ACTION_STATUS_LABELS.get(status) ?? humanize(status);
}

export function runStatusTone(status: string): Tone {
  return RUN_STATUS_TONES.get(status) ?? "neutral";
}

export function verdictTone(verdict: string): Tone {
  return VERDICT_TONES.get(verdict) ?? "neutral";
}
