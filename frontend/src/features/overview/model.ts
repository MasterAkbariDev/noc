import { Bot, Server, Siren, UserRoundCheck, type LucideIcon } from "lucide-react";
import type { ActivityItem, Kpis, MetricsDay, Role, ServerStatus, ServerSummary } from "../../api/types";
import type { Tone } from "../../lib/tones";

export const OVERVIEW_FALLBACK_POLL_MS = 15000;
export const ACTIVITY_LIMIT = 10;

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

const SERVER_STATUSES: ServerStatus[] = ["up", "down", "unknown"];

const SERVER_COLORS: Record<ServerStatus, string> = {
  up: "var(--ui-ok)",
  down: "var(--ui-critical)",
  unknown: "var(--ui-unknown)",
};

export type KpiView = {
  key: string;
  label: string;
  value: string;
  hint: string;
  tone: Tone;
  to: string;
  icon: LucideIcon;
  trend?: number[];
};

export type KpiTrends = { opened: number[]; escalated: number[] };

export type StatusCount = { key: ServerStatus; label: string; value: number; color: string };

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

function llmKpiView(kpis: Kpis, llmMode: string | undefined): KpiView {
  if (llmMode === "replay") {
    return {
      key: "llm",
      label: "LLM keys",
      value: "Replay mode",
      hint: "recorded answers",
      tone: "neutral",
      to: "/system",
      icon: Bot,
    };
  }
  return {
    key: "llm",
    label: "LLM keys",
    value: `${kpis.llm_keys_ok}/${kpis.llm_keys_total}`,
    hint: "working now",
    tone: fractionTone(kpis.llm_keys_ok, kpis.llm_keys_total),
    to: "/system",
    icon: Bot,
  };
}

export function kpiTrends(days: MetricsDay[] | undefined): KpiTrends | undefined {
  if (days === undefined) {
    return undefined;
  }
  return { opened: days.map((day) => day.opened), escalated: days.map((day) => day.escalated) };
}

export function serverStatusCounts(servers: ServerSummary[]): StatusCount[] {
  return SERVER_STATUSES.map((status) => ({
    key: status,
    label: serverLabel(status),
    value: servers.filter((server) => server.status === status).length,
    color: SERVER_COLORS[status],
  }));
}

export function kpiViews(kpis: Kpis, llmMode?: string, trends?: KpiTrends): KpiView[] {
  return [
    {
      key: "open",
      label: "Open incidents",
      value: String(kpis.open_incidents),
      hint: "not closed yet",
      tone: "neutral",
      to: "/incidents?filter=open",
      icon: Siren,
      trend: trends?.opened,
    },
    {
      key: "needs-you",
      label: "Needs you",
      value: String(kpis.needs_you),
      hint: "escalated or waiting for approval",
      tone: kpis.needs_you > 0 ? "warning" : "ok",
      to: "/incidents?filter=needs-you",
      icon: UserRoundCheck,
      trend: trends?.escalated,
    },
    {
      key: "servers",
      label: "Servers",
      value: `${kpis.servers_up}/${kpis.servers_total}`,
      hint: "up now",
      tone: fractionTone(kpis.servers_up, kpis.servers_total),
      to: "/servers",
      icon: Server,
    },
    llmKpiView(kpis, llmMode),
  ];
}
