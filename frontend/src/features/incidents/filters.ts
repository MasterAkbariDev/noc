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

const FINISHED_STATUSES: ReadonlySet<string> = new Set(["RESOLVED", "SELF_RESOLVED", "CLOSED"]);

const NEEDS_YOU_STATUSES: ReadonlySet<string> = new Set(["ESCALATED", "AWAITING_APPROVAL"]);

export function parseFilter(value: string | null): IncidentFilter {
  return INCIDENT_FILTERS.find((filter) => filter === value) ?? DEFAULT_FILTER;
}

export function matchesFilter(incident: IncidentSummary, filter: IncidentFilter): boolean {
  switch (filter) {
    case "open":
      return !FINISHED_STATUSES.has(incident.status);
    case "needs-you":
      return NEEDS_YOU_STATUSES.has(incident.status);
    case "resolved":
      return FINISHED_STATUSES.has(incident.status);
    case "all":
      return true;
  }
}

export function matchesSearch(incident: IncidentSummary, search: string): boolean {
  const needle = search.trim().toLowerCase();
  if (needle === "") {
    return true;
  }
  return incident.title.toLowerCase().includes(needle) || incident.target.toLowerCase().includes(needle);
}

export function matchesSeverity(incident: IncidentSummary, severity: string): boolean {
  return severity === "" || incident.severity === severity;
}

export function rootCauseLabel(code: string): string {
  const text = code.replaceAll("_", " ").toLowerCase();
  return text.charAt(0).toUpperCase() + text.slice(1);
}
