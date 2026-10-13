import { describe, expect, it } from "vitest";
import { healthView, incidentStatusView, severityView } from "./tones";

describe("severityView", () => {
  it("maps the three known severities to a label and a tone", () => {
    expect(severityView("critical")).toEqual({ label: "Critical", tone: "critical" });
    expect(severityView("WARNING")).toEqual({ label: "Warning", tone: "warning" });
    expect(severityView("info")).toEqual({ label: "Info", tone: "info" });
  });

  it("falls back to a neutral humanised label for an unknown severity", () => {
    expect(severityView("very_bad")).toEqual({ label: "Very bad", tone: "neutral" });
  });
});

describe("incidentStatusView", () => {
  it("shows escalated incidents as Needs you", () => {
    expect(incidentStatusView("ESCALATED")).toEqual({ label: "Needs you", tone: "warning" });
  });

  it("marks resolved statuses as ok", () => {
    expect(incidentStatusView("RESOLVED").tone).toBe("ok");
    expect(incidentStatusView("SELF_RESOLVED").tone).toBe("ok");
  });

  it("falls back to a humanised label and the unknown tone", () => {
    expect(incidentStatusView("SOME_NEW_STATE")).toEqual({
      label: "Some new state",
      tone: "unknown",
    });
  });

  it("does not treat object property names as statuses", () => {
    expect(incidentStatusView("constructor")).toEqual({ label: "Constructor", tone: "unknown" });
  });
});

describe("healthView", () => {
  it.each([
    ["ok", "Healthy", "ok"],
    ["degraded", "Degraded", "warning"],
    ["down", "Down", "critical"],
    ["unknown", "Unknown", "unknown"],
  ] as const)("maps %s to %s with tone %s", (status, label, tone) => {
    expect(healthView(status)).toEqual({ label, tone });
  });
});
