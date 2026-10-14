import { describe, expect, it } from "vitest";
import {
  actionStatusLabel,
  EVENT_TYPE_LABELS,
  eventTypeLabel,
  plainLabel,
  runStatusTone,
  verdictTone,
} from "./labels";

const BACKEND_EVENT_TYPES = [
  "incident_opened",
  "alert_attached",
  "state_changed",
  "investigation_planned",
  "specialist_unavailable",
  "specialist_finished",
  "specialist_failed",
  "investigation_abandoned",
  "action_authorized",
  "action_dispatched",
  "action_succeeded",
  "action_failed",
  "action_outcome_unknown",
  "action_cancelled",
  "verification_passed",
  "verification_failed",
  "approval_requested",
  "approval_decided",
  "approval_expired",
  "report_generated",
];

describe("actionStatusLabel", () => {
  it("gives a plain label for a known action status", () => {
    expect(actionStatusLabel("pending_approval")).toBe("Waiting for approval");
    expect(actionStatusLabel("ineligible")).toBe("Not allowed");
  });

  it("humanises a status it does not know", () => {
    expect(actionStatusLabel("some_new_state")).toBe("Some new state");
  });
});

describe("eventTypeLabel", () => {
  it("gives plain labels for approval and action events", () => {
    expect(eventTypeLabel("approval_requested")).toBe("Approval requested");
    expect(eventTypeLabel("approval_decided")).toBe("Decision recorded");
    expect(eventTypeLabel("action_authorized")).toBe("Action approved");
    expect(eventTypeLabel("verification_failed")).toBe("Check after the fix failed");
  });

  it("has a plain label for every event type the backend writes", () => {
    for (const type of BACKEND_EVENT_TYPES) {
      expect(EVENT_TYPE_LABELS.has(type), type).toBe(true);
      expect(eventTypeLabel(type)).not.toMatch(/_/);
    }
  });

  it("humanises an event type it does not know", () => {
    expect(eventTypeLabel("note")).toBe("Note");
  });

  it("does not treat object property names as event types", () => {
    expect(eventTypeLabel("constructor")).toBe("Constructor");
  });
});

describe("plainLabel", () => {
  it("turns a machine code into a sentence-case label", () => {
    expect(plainLabel("restart_service")).toBe("Restart service");
    expect(plainLabel("REQUIRES_APPROVAL")).toBe("Requires approval");
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
