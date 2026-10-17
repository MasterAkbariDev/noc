import type { LlmCheck, LlmKeyTier, LlmManagedKey, LlmProxySource } from "../../api/types";
import type { Tone } from "../../lib/tones";

const TIER_LABELS: Record<LlmKeyTier, string> = {
  free: "Free tier",
  paid: "Paid tier",
};
const PROXY_SOURCE_LABELS: Record<LlmProxySource, string> = {
  env: "from the environment",
  panel: "set in the panel",
  none: "no proxy",
};

export const KEY_TIERS: readonly LlmKeyTier[] = ["free", "paid"];

export function tierLabel(tier: LlmKeyTier): string {
  return TIER_LABELS[tier];
}

export function tierTone(tier: LlmKeyTier): Tone {
  return tier === "paid" ? "info" : "neutral";
}

export function proxySourceLabel(source: LlmProxySource): string {
  return PROXY_SOURCE_LABELS[source];
}

export function keyTitle(key: LlmManagedKey): string {
  return key.name ?? `${key.provider} key`;
}

export function keySourceLabel(key: LlmManagedKey): string {
  return key.source === "panel" ? "Added in the panel" : "Environment (read-only)";
}

export function maskedKey(key: LlmManagedKey): string {
  return `…${key.last4}`;
}

export function checkSummary(check: LlmCheck): string {
  const timing = check.latency_ms > 0 ? ` in ${(check.latency_ms / 1000).toFixed(1)} s` : "";
  const model = check.model ? ` (${check.model})` : "";
  return check.ok ? `Works${timing}${model}: ${check.detail}` : `Failed${timing}${model}: ${check.detail}`;
}

const CHAIN_HEADINGS: Record<string, string> = {
  small: "Small tier: specialist agents",
  strong: "Strong tier: diagnosis and investigation",
};

export function chainHeading(tier: string): string {
  return CHAIN_HEADINGS[tier] ?? `${tier} tier`;
}

export function parseTier(value: string): LlmKeyTier {
  return value === "paid" ? "paid" : "free";
}
