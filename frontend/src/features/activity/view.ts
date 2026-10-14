import type { ActivityVerify } from "../../api/types";
import type { Tone } from "../../lib/tones";
import type { ActivityFilters } from "./filters";

export type ChainView = { label: string; tone: Tone };

export function chainView(verify: ActivityVerify): ChainView {
  if (verify.ok) {
    return { label: "Audit log intact", tone: "ok" };
  }
  if (verify.broken_at === null) {
    return { label: "Audit log broken", tone: "critical" };
  }
  return { label: `Audit log broken at entry ${verify.broken_at}`, tone: "critical" };
}

export function emptyFeedText(filters: ActivityFilters): string {
  return filters.action === "" && filters.actor === ""
    ? "No activity yet."
    : "No activity matches these filters.";
}
