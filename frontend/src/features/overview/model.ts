import type { ActivityItem, Kpis, Role, ServerStatus, VerdictLevel } from "../../api/types";
import type { Tone } from "../../lib/tones";

export const OVERVIEW_FALLBACK_POLL_MS = 15000;
export const ACTIVITY_LIMIT = 15;

const VERDICT_TONES: Record<VerdictLevel, Tone> = {
  ok: "ok",
  attention: "warning",
  degraded: "warning",
  down: "critical",
};

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

export type KpiView = {
  key: string;
  label: string;
  value: string;
  hint: string;
  tone: Tone;
  to: string;
};

export function verdictTone(level: VerdictLevel): Tone {
  return VERDICT_TONES[level];
}

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

function fractionTone(healthy: number, total: number): Tone {
  if (total === 0) {
    return "neutral";
  }
  return healthy === total ? "ok" : "warning";
}

export function kpiViews(kpis: Kpis): KpiView[] {
  return [
    {
      key: "open",
      label: "Open incidents",
      value: String(kpis.open_incidents),
      hint: "not closed yet",
      tone: "neutral",
      to: "/incidents?filter=open",
    },
    {
      key: "needs-you",
      label: "Needs you",
      value: String(kpis.needs_you),
      hint: "escalated or waiting for approval",
      tone: kpis.needs_you > 0 ? "warning" : "ok",
      to: "/incidents?filter=needs-you",
    },
    {
      key: "servers",
      label: "Servers",
      value: `${kpis.servers_up}/${kpis.servers_total}`,
      hint: "up now",
      tone: fractionTone(kpis.servers_up, kpis.servers_total),
      to: "/servers",
    },
    {
      key: "llm",
      label: "LLM keys",
      value: `${kpis.llm_keys_ok}/${kpis.llm_keys_total}`,
      hint: "working now",
      tone: fractionTone(kpis.llm_keys_ok, kpis.llm_keys_total),
      to: "/system",
    },
  ];
}
