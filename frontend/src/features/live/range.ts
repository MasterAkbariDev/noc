import { useSearchParams } from "react-router";
import type { LivePoint, LiveRange } from "../../api/types";
import type { SelectOption } from "../../ui";

export const LIVE_RANGES: LiveRange[] = ["15m", "1h", "24h"];
export const DEFAULT_RANGE: LiveRange = "1h";

export const RANGE_OPTIONS: SelectOption[] = [
  { value: "15m", label: "Last 15 minutes" },
  { value: "1h", label: "Last hour" },
  { value: "24h", label: "Last 24 hours" },
];

const RANGE_SECONDS: Record<LiveRange, number> = { "15m": 900, "1h": 3600, "24h": 86400 };
const REFRESH_MS: Record<LiveRange, number> = { "15m": 15_000, "1h": 30_000, "24h": 60_000 };

export function parseRange(value: string | null): LiveRange {
  return LIVE_RANGES.find((range) => range === value) ?? DEFAULT_RANGE;
}

export function rangeSeconds(range: LiveRange): number {
  return RANGE_SECONDS[range];
}

export function refreshMs(range: LiveRange): number {
  return REFRESH_MS[range];
}

export function lastValue(points: LivePoint[]): number | null {
  return points.at(-1)?.[1] ?? null;
}

export function sumSeries(left: LivePoint[], right: LivePoint[]): LivePoint[] {
  const extra = new Map(right);
  return left.map(([time, value]) => [time, value + (extra.get(time) ?? 0)]);
}

export function useLiveRange(): [LiveRange, (range: LiveRange) => void] {
  const [params, setParams] = useSearchParams();
  const range = parseRange(params.get("range"));
  function setRange(next: LiveRange) {
    setParams(
      (previous) => {
        const updated = new URLSearchParams(previous);
        updated.set("range", next);
        return updated;
      },
      { replace: true },
    );
  }
  return [range, setRange];
}
