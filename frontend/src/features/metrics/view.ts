import type { Metrics, MetricsDay } from "../../api/types";
import type { ColumnPoint } from "../../ui/charts";
import { rootCauseLabel } from "../incidents/filters";
import { incidentStatusView } from "../../lib/tones";

export const RANGE_OPTIONS = [7, 14, 30, 90] as const;
export const DEFAULT_RANGE = 14;

const VARIANT_LABELS: Record<string, string> = {
  single: "Single agent",
  multi: "Multi-agent",
  "multi-strong": "Multi-agent (strong model)",
  runbook: "Runbook (no model)",
};

const ACTION_LABELS: Record<string, string> = {
  succeeded: "Done",
  ineligible: "Blocked by the policy",
  failed: "Failed",
  refused: "Refused by the server",
  rejected: "Rejected by a person",
  expired: "Approval expired",
  cancelled: "Cancelled",
  pending_approval: "Waiting for approval",
  proposed: "Proposed",
  outcome_unknown: "Outcome unknown",
  other: "Other",
};

export function parseRange(value: string | null): number {
  const parsed = Number(value);
  return RANGE_OPTIONS.find((option) => option === parsed) ?? DEFAULT_RANGE;
}

function shortDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  return date.toLocaleDateString("en", { month: "short", day: "numeric", timeZone: "UTC" });
}

function longDay(day: string): string {
  const date = new Date(`${day}T00:00:00Z`);
  return date.toLocaleDateString("en", { weekday: "short", month: "short", day: "numeric", timeZone: "UTC" });
}

export function dayPoints(days: MetricsDay[], pick: (day: MetricsDay) => number[]): ColumnPoint[] {
  return days.map((day) => ({ key: day.day, label: shortDay(day.day), longLabel: longDay(day.day), values: pick(day) }));
}

export function variantLabel(variant: string): string {
  return VARIANT_LABELS[variant] ?? variant;
}

export function actionLabel(status: string): string {
  return ACTION_LABELS[status] ?? rootCauseLabel(status);
}

export function causeLabel(code: string): string {
  return code === "other" ? "Other" : rootCauseLabel(code);
}

export function outcomeLabel(status: string): string {
  return status === "other" ? "Other" : incidentStatusView(status).label;
}

export function percent(value: number | null): string {
  return value === null ? "–" : `${Math.round(value * 100)}%`;
}

export function minutes(value: number | null): string {
  if (value === null) {
    return "–";
  }
  if (value < 1) {
    return `${Math.round(value * 60)} s`;
  }
  if (value < 120) {
    return `${value.toFixed(value < 10 ? 1 : 0)} min`;
  }
  return `${(value / 60).toFixed(1)} h`;
}

export function resolvedHint(metrics: Metrics): string {
  const finished = metrics.totals.resolved + metrics.totals.escalated;
  return finished === 0 ? "No finished incidents yet" : `${metrics.totals.resolved} of ${finished} finished incidents`;
}
