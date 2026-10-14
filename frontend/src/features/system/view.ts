import type { SystemHealth } from "../../api/types";
import type { ToneView } from "../../lib/tones";

type Verdict = SystemHealth["verdict"];

const VERDICT_VIEWS: Record<Verdict, ToneView> = {
  ok: { label: "Everything is working", tone: "ok" },
  degraded: { label: "Some parts are degraded", tone: "warning" },
  down: { label: "Something is down", tone: "critical" },
};

const MODE_VIEWS = new Map<string, ToneView>([
  ["live", { label: "Live", tone: "ok" }],
  ["record", { label: "Recording", tone: "info" }],
  ["replay", { label: "Replay", tone: "warning" }],
]);

const KEY_STATE_VIEWS = new Map<string, ToneView>([
  ["ok", { label: "Working", tone: "ok" }],
  ["cooling", { label: "Cooling down", tone: "warning" }],
  ["rejected", { label: "Rejected", tone: "critical" }],
  ["unused", { label: "Not used yet", tone: "neutral" }],
]);

export function verdictView(verdict: Verdict): ToneView {
  return VERDICT_VIEWS[verdict];
}

export function llmModeView(mode: string): ToneView {
  return MODE_VIEWS.get(mode) ?? { label: mode, tone: "unknown" };
}

export function keyStateView(state: string): ToneView {
  return KEY_STATE_VIEWS.get(state) ?? { label: state, tone: "unknown" };
}

export function usagePercent(usedToday: number, dailyLimit: number): number {
  if (dailyLimit <= 0) {
    return 0;
  }
  return Math.min(100, Math.max(0, (usedToday / dailyLimit) * 100));
}

export function usageText(usedToday: number, dailyLimit: number): string {
  return `${usedToday} of ${dailyLimit} used today`;
}
