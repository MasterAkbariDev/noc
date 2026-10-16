import { describe, expect, it } from "vitest";
import { lastValue, parseRange, rangeSeconds, refreshMs, sumSeries } from "./range";

describe("live range", () => {
  it("accepts the three ranges and falls back to the last hour", () => {
    expect(parseRange("15m")).toBe("15m");
    expect(parseRange("24h")).toBe("24h");
    expect(parseRange("7d")).toBe("1h");
    expect(parseRange(null)).toBe("1h");
  });

  it("refreshes a short range more often than a long one", () => {
    expect(refreshMs("15m")).toBeLessThan(refreshMs("24h"));
    expect(rangeSeconds("24h")).toBe(86_400);
  });

  it("reads the newest value and adds two series point by point", () => {
    expect(lastValue([[1, 3], [2, 5]])).toBe(5);
    expect(lastValue([])).toBeNull();
    expect(sumSeries([[1, 3], [2, 5]], [[1, 1]])).toEqual([[1, 4], [2, 5]]);
  });
});
