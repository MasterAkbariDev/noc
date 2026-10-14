export type Tone = "critical" | "warning" | "info" | "ok" | "neutral" | "unknown";

export type ToneView = { label: string; tone: Tone };

export type HealthStatus = "ok" | "degraded" | "down" | "unknown";

const SEVERITY_VIEWS = new Map<string, ToneView>([
  ["critical", { label: "Critical", tone: "critical" }],
  ["warning", { label: "Warning", tone: "warning" }],
  ["info", { label: "Info", tone: "info" }],
]);

const INCIDENT_STATUS_VIEWS = new Map<string, ToneView>([
  ["NEW", { label: "New", tone: "info" }],
  ["INVESTIGATING", { label: "Investigating", tone: "info" }],
  ["DIAGNOSED", { label: "Diagnosed", tone: "info" }],
  ["PLANNED", { label: "Planned", tone: "info" }],
  ["AWAITING_APPROVAL", { label: "Waiting for approval", tone: "warning" }],
  ["REMEDIATING", { label: "Taking action", tone: "info" }],
  ["VERIFYING", { label: "Checking the fix", tone: "info" }],
  ["RESOLVED", { label: "Resolved", tone: "ok" }],
  ["SELF_RESOLVED", { label: "Resolved by itself", tone: "ok" }],
  ["ESCALATED", { label: "Needs you", tone: "warning" }],
  ["CLOSED", { label: "Closed", tone: "neutral" }],
]);

const HEALTH_VIEWS: Record<HealthStatus, ToneView> = {
  ok: { label: "Healthy", tone: "ok" },
  degraded: { label: "Degraded", tone: "warning" },
  down: { label: "Down", tone: "critical" },
  unknown: { label: "Unknown", tone: "unknown" },
};

function humanize(code: string): string {
  const text = code.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export function severityView(severity: string): ToneView {
  return SEVERITY_VIEWS.get(severity.toLowerCase()) ?? { label: humanize(severity), tone: "neutral" };
}

export function incidentStatusView(status: string): ToneView {
  return INCIDENT_STATUS_VIEWS.get(status) ?? { label: humanize(status), tone: "unknown" };
}

export function healthView(status: HealthStatus): ToneView {
  return HEALTH_VIEWS[status];
}

export type OverviewLevel = "ok" | "working" | "attention" | "degraded" | "down";

const OVERVIEW_LEVEL_VIEWS: Record<OverviewLevel, Tone> = {
  ok: "ok",
  working: "info",
  attention: "warning",
  degraded: "warning",
  down: "critical",
};

const STORY_VERDICT_VIEWS = new Map<string, Tone>([
  ["approval", "warning"],
  ["waiting", "neutral"],
  ["running", "info"],
  ["ran", "ok"],
  ["failed", "critical"],
  ["blocked", "warning"],
  ["unknown", "warning"],
  ["rejected", "warning"],
  ["expired", "neutral"],
  ["cancelled", "neutral"],
]);

export function overviewTone(level: OverviewLevel): Tone {
  return OVERVIEW_LEVEL_VIEWS[level];
}

export function storyVerdictTone(verdict: string): Tone {
  return STORY_VERDICT_VIEWS.get(verdict) ?? "neutral";
}
