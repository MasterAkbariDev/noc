import { describe, expect, it } from "vitest";
import { keyStateView, llmModeView, usagePercent, usageText, verdictView } from "./view";

describe("verdictView", () => {
  it("maps each verdict to a sentence and a tone", () => {
    expect(verdictView("ok")).toEqual({ label: "Everything is working", tone: "ok" });
    expect(verdictView("degraded")).toEqual({ label: "Some parts are degraded", tone: "warning" });
    expect(verdictView("down")).toEqual({ label: "Something is down", tone: "critical" });
  });
});

describe("llmModeView", () => {
  it("names the live, recording and replay modes", () => {
    expect(llmModeView("live").label).toBe("Live");
    expect(llmModeView("record").label).toBe("Recording");
    expect(llmModeView("replay")).toEqual({ label: "Replay", tone: "warning" });
  });

  it("shows an unknown mode as its own text with the unknown tone", () => {
    expect(llmModeView("<script>x</script>")).toEqual({ label: "<script>x</script>", tone: "unknown" });
  });
});

describe("keyStateView", () => {
  it("maps each key state to a label and a tone", () => {
    expect(keyStateView("ok")).toEqual({ label: "Working", tone: "ok" });
    expect(keyStateView("cooling")).toEqual({ label: "Cooling down", tone: "warning" });
    expect(keyStateView("rejected")).toEqual({ label: "Rejected", tone: "critical" });
    expect(keyStateView("unused")).toEqual({ label: "Not used yet", tone: "neutral" });
  });

  it("falls back to the raw value for a state it does not know", () => {
    expect(keyStateView("retired")).toEqual({ label: "retired", tone: "unknown" });
  });
});

describe("usagePercent", () => {
  it("is the share of the daily limit that is used", () => {
    expect(usagePercent(25, 100)).toBe(25);
    expect(usagePercent(0, 100)).toBe(0);
  });

  it("is capped at 100 when the limit is passed", () => {
    expect(usagePercent(150, 100)).toBe(100);
  });

  it("is zero when the limit is zero or negative, so no division by zero shows", () => {
    expect(usagePercent(5, 0)).toBe(0);
    expect(usagePercent(5, -1)).toBe(0);
  });
});

describe("usageText", () => {
  it("reads as used of limit today", () => {
    expect(usageText(12, 100)).toBe("12 of 100 used today");
  });
});
