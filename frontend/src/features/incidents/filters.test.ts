import { describe, expect, it } from "vitest";
import type { IncidentSummary } from "../../api/types";
import { matchesSeverity, parseFilter, rootCauseLabel, statusesFor } from "./filters";

function incident(status: string, overrides: Partial<IncidentSummary> = {}): IncidentSummary {
  return {
    id: `id-${status}`,
    title: `Incident ${status}`,
    status,
    severity: "warning",
    target: "web-1",
    opened_at: "2026-10-12T10:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
    ...overrides,
  };
}

const FINISHED = ["RESOLVED", "SELF_RESOLVED", "CLOSED"];

describe("parseFilter", () => {
  it("accepts the four filters and falls back to open for anything else", () => {
    expect(parseFilter("needs-you")).toBe("needs-you");
    expect(parseFilter("resolved")).toBe("resolved");
    expect(parseFilter("all")).toBe("all");
    expect(parseFilter("open")).toBe("open");
    expect(parseFilter(null)).toBe("open");
    expect(parseFilter("bogus")).toBe("open");
  });
});

describe("statusesFor", () => {
  it("open is every status except the three finished ones", () => {
    const open = statusesFor("open");

    expect(open).toEqual([
      "NEW",
      "INVESTIGATING",
      "DIAGNOSED",
      "PLANNED",
      "AWAITING_APPROVAL",
      "REMEDIATING",
      "VERIFYING",
      "ESCALATED",
    ]);
    for (const status of FINISHED) {
      expect(open).not.toContain(status);
    }
  });

  it("needs you is escalated and waiting for approval", () => {
    expect(statusesFor("needs-you")).toEqual(["ESCALATED", "AWAITING_APPROVAL"]);
  });

  it("resolved is the three finished statuses and all sends no status filter", () => {
    expect(statusesFor("resolved")).toEqual(FINISHED);
    expect(statusesFor("all")).toEqual([]);
  });

  it("returns a fresh array each time so a caller cannot change the table", () => {
    statusesFor("open").push("BOGUS");

    expect(statusesFor("open")).not.toContain("BOGUS");
  });
});

describe("matchesSeverity", () => {
  it("accepts every row when no severity is chosen", () => {
    expect(matchesSeverity(incident("NEW", { severity: "info" }), "")).toBe(true);
    expect(matchesSeverity(incident("NEW", { severity: "info" }), "critical")).toBe(false);
    expect(matchesSeverity(incident("NEW", { severity: "critical" }), "critical")).toBe(true);
  });
});

describe("rootCauseLabel", () => {
  it("turns a root cause code into a sentence-case label", () => {
    expect(rootCauseLabel("disk_full_logs")).toBe("Disk full logs");
    expect(rootCauseLabel("service_crashed")).toBe("Service crashed");
  });
});
