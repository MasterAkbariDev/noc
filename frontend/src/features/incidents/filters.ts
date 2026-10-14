import type { IncidentSummary } from "../../api/types";

export const INCIDENT_FILTERS = ["open", "needs-you", "resolved", "all"] as const;

export type IncidentFilter = (typeof INCIDENT_FILTERS)[number];

export const DEFAULT_FILTER: IncidentFilter = "open";

export const FILTER_LABELS: Record<IncidentFilter, string> = {
  open: "Open",
  "needs-you": "Needs you",
  resolved: "Resolved",
  all: "All",
};

export const FILTER_EMPTY_TEXT: Record<IncidentFilter, string> = {
  open: "No open incidents. All quiet.",
  "needs-you": "Nothing needs you right now.",
  resolved: "No resolved incidents.",
  all: "No incidents yet.",
};

const OPEN_STATUSES = [
  "NEW",
  "INVESTIGATING",
  "DIAGNOSED",
  "PLANNED",
  "AWAITING_APPROVAL",
  "REMEDIATING",
  "VERIFYING",
  "ESCALATED",
] as const;

const NEEDS_YOU_STATUSES = ["ESCALATED", "AWAITING_APPROVAL"] as const;

const FINISHED_STATUSES = ["RESOLVED", "SELF_RESOLVED", "CLOSED"] as const;

export function parseFilter(value: string | null): IncidentFilter {
  return INCIDENT_FILTERS.find((filter) => filter === value) ?? DEFAULT_FILTER;
}

export function statusesFor(filter: IncidentFilter): string[] {
  switch (filter) {
    case "open":
      return [...OPEN_STATUSES];
    case "needs-you":
      return [...NEEDS_YOU_STATUSES];
    case "resolved":
      return [...FINISHED_STATUSES];
    case "all":
      return [];
  }
}

export function matchesSeverity(incident: IncidentSummary, severity: string): boolean {
  return severity === "" || incident.severity === severity;
}

export function rootCauseLabel(code: string): string {
  const text = code.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
