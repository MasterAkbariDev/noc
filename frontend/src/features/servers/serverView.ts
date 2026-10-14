import { ApiError } from "../../api/client";
import type { ServerStatus, ServiceState } from "../../api/types";
import type { Tone, ToneView } from "../../lib/tones";

export const ATTENTION_PERCENT = 90;
export const UNREACHABLE_MESSAGE = "The NOC could not be reached.";
export const NOT_FOUND_MESSAGE = "This server is not known to the NOC.";

const STATUS_VIEWS: Record<ServerStatus, ToneView> = {
  up: { label: "Reachable", tone: "ok" },
  down: { label: "Not reachable", tone: "critical" },
  unknown: { label: "Unknown", tone: "unknown" },
};

export function serverStatusView(status: ServerStatus): ToneView {
  return STATUS_VIEWS[status];
}

export function serviceView(up: ServiceState["up"]): ToneView {
  if (up === null) {
    return { label: "Unknown", tone: "unknown" };
  }
  return up ? { label: "Up", tone: "ok" } : { label: "Down", tone: "critical" };
}

export function environmentTone(environment: string): Tone {
  return environment === "prod" ? "warning" : "neutral";
}

export function isAttention(percent: number): boolean {
  return percent >= ATTENTION_PERCENT;
}

export function clampPercent(percent: number): number {
  return Math.min(100, Math.max(0, percent));
}

export function openIncidentsText(count: number): string {
  if (count === 0) {
    return "No open incidents";
  }
  return count === 1 ? "1 open incident" : `${count} open incidents`;
}

const HEADLINE_SEPARATOR = " · ";

export function headlineWithoutIncidents(headline: string, count: number): string {
  const phrase = openIncidentsText(count);
  if (headline === phrase) {
    return "";
  }
  const suffix = `${HEADLINE_SEPARATOR}${phrase}`;
  return headline.endsWith(suffix) ? headline.slice(0, -suffix.length) : headline;
}

export function errorText(error: unknown): string {
  return error instanceof ApiError ? error.detail : UNREACHABLE_MESSAGE;
}

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && error.status === 404;
}
