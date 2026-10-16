import type { ActivityItem, Role, ServerStatus } from "../../api/types";
import type { Tone } from "../../lib/tones";

export const OVERVIEW_FALLBACK_POLL_MS = 15000;
export const ACTIVITY_LIMIT = 8;

const SERVER_TONES: Record<ServerStatus, Tone> = {
  up: "ok",
  down: "critical",
  unknown: "unknown",
};

const SERVER_LABELS: Record<ServerStatus, string> = {
  up: "Up",
  down: "Down",
  unknown: "Unknown",
};

export const TREND_DAYS = 14;

export function serverTone(status: ServerStatus): Tone {
  return SERVER_TONES[status];
}

export function serverLabel(status: ServerStatus): string {
  return SERVER_LABELS[status];
}

export function canCloseIncidents(role: Role): boolean {
  return role === "operator" || role === "admin";
}

export function recentActivity(items: ActivityItem[]): ActivityItem[] {
  return items.slice(0, ACTIVITY_LIMIT);
}
