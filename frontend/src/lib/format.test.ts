import { describe, expect, it } from "vitest";
import {
  absoluteTime,
  durationMs,
  percentFromFraction,
  percentFromHundred,
  relativeTime,
} from "./format";

const NOW = new Date("2026-10-13T12:00:00Z");

function minutesBefore(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString();
}

describe("relativeTime", () => {
  it.each([
    [30 * 1_000, "just now"],
    [12 * 60_000, "12 min ago"],
    [3 * 60 * 60_000, "3 h ago"],
    [25 * 60 * 60_000, "1 day ago"],
    [50 * 60 * 60_000, "2 days ago"],
  ])("formats %i ms ago as %s", (elapsedMs, expected) => {
    const iso = new Date(NOW.getTime() - elapsedMs).toISOString();
    expect(relativeTime(iso, NOW)).toBe(expected);
  });

  it("treats a time in the future as just now", () => {
    expect(relativeTime(new Date(NOW.getTime() + 5 * 60_000).toISOString(), NOW)).toBe("just now");
  });

  it("returns the input when it is not a date", () => {
    expect(relativeTime("not a date", NOW)).toBe("not a date");
  });

  it("uses minutes for the first hour", () => {
    expect(relativeTime(minutesBefore(59), NOW)).toBe("59 min ago");
  });
});

describe("absoluteTime", () => {
  it("formats a valid time with the locale string", () => {
    const iso = "2026-10-13T12:00:00Z";
    expect(absoluteTime(iso)).toBe(new Date(iso).toLocaleString());
  });

  it("returns the input when it is not a date", () => {
    expect(absoluteTime("yesterday-ish")).toBe("yesterday-ish");
  });
});

describe("percent", () => {
  it("rounds a fraction between 0 and 1", () => {
    expect(percentFromFraction(0.923)).toBe("92%");
    expect(percentFromFraction(1)).toBe("100%");
  });

  it("rounds a value between 0 and 100", () => {
    expect(percentFromHundred(92.4)).toBe("92%");
    expect(percentFromHundred(7)).toBe("7%");
  });
});

describe("durationMs", () => {
  it.each([
    [-5, "0 ms"],
    [250, "250 ms"],
    [1_500, "1.5 s"],
    [61_000, "1 min 1 s"],
    [119_500, "2 min 0 s"],
  ])("formats %i ms as %s", (ms, expected) => {
    expect(durationMs(ms)).toBe(expected);
  });
});
