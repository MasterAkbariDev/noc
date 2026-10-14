import { describe, expect, it } from "vitest";
import type { IncidentSummary } from "../../api/types";
import { matchesFilter, matchesSearch, matchesSeverity, parseFilter, rootCauseLabel } from "./filters";

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

describe("matchesFilter", () => {
  it("open is every status except the three finished ones", () => {
    const open = ["NEW", "INVESTIGATING", "DIAGNOSED", "PLANNED", "AWAITING_APPROVAL", "REMEDIATING", "VERIFYING", "ESCALATED"];
    for (const status of open) {
      expect(matchesFilter(incident(status), "open")).toBe(true);
    }
    for (const status of ["RESOLVED", "SELF_RESOLVED", "CLOSED"]) {
      expect(matchesFilter(incident(status), "open")).toBe(false);
    }
  });

  it("needs you is escalated and waiting for approval", () => {
    expect(matchesFilter(incident("ESCALATED"), "needs-you")).toBe(true);
    expect(matchesFilter(incident("AWAITING_APPROVAL"), "needs-you")).toBe(true);
    expect(matchesFilter(incident("INVESTIGATING"), "needs-you")).toBe(false);
    expect(matchesFilter(incident("RESOLVED"), "needs-you")).toBe(false);
  });

  it("resolved is the three finished statuses and all shows everything", () => {
    expect(matchesFilter(incident("RESOLVED"), "resolved")).toBe(true);
    expect(matchesFilter(incident("SELF_RESOLVED"), "resolved")).toBe(true);
    expect(matchesFilter(incident("CLOSED"), "resolved")).toBe(true);
    expect(matchesFilter(incident("NEW"), "resolved")).toBe(false);
    expect(matchesFilter(incident("NEW"), "all")).toBe(true);
    expect(matchesFilter(incident("CLOSED"), "all")).toBe(true);
  });
});

describe("matchesSearch", () => {
  const row = incident("NEW", { title: "Disk almost full", target: "demo-1" });

  it("matches the title or the target, ignoring case and surrounding spaces", () => {
    expect(matchesSearch(row, "")).toBe(true);
    expect(matchesSearch(row, "  DISK ")).toBe(true);
    expect(matchesSearch(row, "demo")).toBe(true);
    expect(matchesSearch(row, "backup")).toBe(false);
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
