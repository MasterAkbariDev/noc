import { describe, expect, it } from "vitest";
import { actionStatusLabel, runStatusTone, verdictTone } from "./labels";

describe("actionStatusLabel", () => {
  it("gives a plain label for a known action status", () => {
    expect(actionStatusLabel("pending_approval")).toBe("Waiting for approval");
    expect(actionStatusLabel("ineligible")).toBe("Not allowed");
  });

  it("humanises a status it does not know", () => {
    expect(actionStatusLabel("some_new_state")).toBe("Some new state");
  });
});

describe("tones", () => {
  it("maps a failed run to critical and an unknown run to neutral", () => {
    expect(runStatusTone("failed")).toBe("critical");
    expect(runStatusTone("odd")).toBe("neutral");
  });

  it("maps verdicts to tones and falls back to neutral", () => {
    expect(verdictTone("ran")).toBe("ok");
    expect(verdictTone("blocked")).toBe("warning");
    expect(verdictTone("unknown")).toBe("neutral");
  });
});
