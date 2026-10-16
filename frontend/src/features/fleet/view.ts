import type { FleetEnvironment, FleetRow, SshKey, SshKeyPurpose, SshKeyRule, SshKeyState } from "../../api/fleet";
import type { Tone } from "../../lib/tones";

const DAY_MS = 24 * 60 * 60 * 1000;

export const FLEET_KEY = "fleet";
export const KEY_PURPOSES: SshKeyPurpose[] = ["ops", "bootstrap", "operator-shell"];
export const ENVIRONMENTS: FleetEnvironment[] = ["lab", "prod"];

const PURPOSE_LABELS: Record<SshKeyPurpose, string> = {
  bootstrap: "Bootstrap",
  ops: "Ops",
  "operator-shell": "Operator shell",
};

const PURPOSE_HINTS: Record<SshKeyPurpose, string> = {
  bootstrap: "Short-lived, only to set a new server up. Revoke it once the helper is running.",
  ops: "Day-to-day key for the ops user, pinned to the NOC's address. The ops user never gets sudo.",
  "operator-shell": "For your own commands later (Telegram). Generated now, installed in a later phase.",
};

const STATE_VIEWS: Record<SshKeyState, { label: string; tone: Tone }> = {
  active: { label: "In date", tone: "ok" },
  rotate_soon: { label: "Rotate soon", tone: "warning" },
  rotating: { label: "Being rotated", tone: "info" },
  expired: { label: "Expired", tone: "critical" },
  retired: { label: "Retired", tone: "neutral" },
};

export function purposeLabel(purpose: SshKeyPurpose): string {
  return PURPOSE_LABELS[purpose];
}

export function purposeHint(purpose: SshKeyPurpose): string {
  return PURPOSE_HINTS[purpose];
}

export function parsePurpose(value: string): SshKeyPurpose {
  return KEY_PURPOSES.find((purpose) => purpose === value) ?? "ops";
}

export function parseEnvironment(value: string): FleetEnvironment {
  return value === "prod" ? "prod" : "lab";
}

export function environmentLabel(environment: FleetEnvironment): string {
  return environment === "prod" ? "Production" : "Lab";
}

export function stateView(state: SshKeyState): { label: string; tone: Tone } {
  return STATE_VIEWS[state];
}

export function dayDistance(iso: string, now: Date = new Date()): string {
  const days = Math.round((Date.parse(iso) - now.getTime()) / DAY_MS);
  if (Number.isNaN(days)) {
    return iso;
  }
  if (days === 0) {
    return "today";
  }
  if (days > 0) {
    return days === 1 ? "in 1 day" : `in ${days} days`;
  }
  return days === -1 ? "1 day ago" : `${-days} days ago`;
}

export function yesNoView(value: boolean | null, yes: string, no: string): { label: string; tone: Tone } {
  if (value === null) {
    return { label: "Unknown", tone: "unknown" };
  }
  return value ? { label: yes, tone: "ok" } : { label: no, tone: "critical" };
}

export function helperView(row: FleetRow): { label: string; tone: Tone } {
  if (row.target_id === null) {
    return { label: "Not set up", tone: "neutral" };
  }
  const version = row.helper_version === null ? "" : ` · ${row.helper_version}`;
  if (row.helper_up === null) {
    return { label: `Unknown${version}`, tone: "unknown" };
  }
  return row.helper_up ? { label: `Up${version}`, tone: "ok" } : { label: `Down${version}`, tone: "critical" };
}

export function sudoView(row: FleetRow): { label: string; tone: Tone } {
  if (row.keys.length === 0) {
    return { label: "Not checked", tone: "neutral" };
  }
  return row.keys.every((key) => key.sudo_scope_ok)
    ? { label: "No sudo", tone: "ok" }
    : { label: "Check sudoers", tone: "warning" };
}

export function sshLine(row: FleetRow): string | null {
  if (row.ssh_user === null || row.ssh_port === null) {
    return null;
  }
  return `${row.ssh_user}@${row.address}:${row.ssh_port}`;
}

export function keysForHost(keys: SshKey[], rules: SshKeyRule[], row: FleetRow): SshKey[] {
  const installable = new Set(rules.filter((rule) => rule.has_paste_command).map((rule) => rule.purpose));
  return keys.filter(
    (key) => key.retired_at === null && key.environment === row.environment && installable.has(key.purpose),
  );
}

export function ruleFor(rules: SshKeyRule[], purpose: SshKeyPurpose): SshKeyRule | undefined {
  return rules.find((rule) => rule.purpose === purpose);
}

export function shortFingerprint(fingerprint: string): string {
  return fingerprint.length > 20 ? `${fingerprint.slice(0, 20)}…` : fingerprint;
}

export function waitingRotation(keys: SshKey[], key: SshKey): SshKey | undefined {
  return keys.find((other) => other.replaces_id === key.id && other.retired_at === null);
}

export function finishesRotation(keys: SshKey[], key: SshKey): boolean {
  return key.replaces_id !== null && keys.some((other) => other.id === key.replaces_id && other.retired_at === null);
}
