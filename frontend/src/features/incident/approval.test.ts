import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import type { ActionView } from "../../api/types";
import {
  CHANGED_REQUEST_TEXT,
  canDecideActions,
  decisionErrorMessage,
  expiryText,
  isExpired,
  pendingApprovals,
} from "./approval";

const NOW = Date.parse("2026-10-14T10:00:00Z");
const MINUTE = 60_000;
const HOUR = 60 * MINUTE;
const DAY = 24 * HOUR;

function action(overrides: Partial<ActionView> = {}): ActionView {
  return {
    id: "act-1",
    action_hash: "a".repeat(64),
    rung: 1,
    authorization: null,
    approval_expires_at: null,
    dispatched_at: null,
    finished_at: null,
    result_code: null,
    action_type: "restart_service",
    resource_id: "web-1:nginx",
    status: "pending_approval",
    permission_class: "REQUIRES_APPROVAL",
    eligible: true,
    gate_failures: [],
    reasons: [],
    impact_score: 3,
    high_impact: false,
    auto_executable: false,
    policy_version: "2026-10-skeleton-1",
    ...overrides,
  };
}

describe("pendingApprovals", () => {
  it("keeps only the actions that wait for approval", () => {
    const waiting = action({ id: "a1" });
    const done = action({ id: "a2", status: "succeeded" });

    expect(pendingApprovals([waiting, done]).map((item) => item.id)).toEqual(["a1"]);
  });
});

describe("canDecideActions", () => {
  it("lets an operator and an admin decide, and not a viewer", () => {
    expect(canDecideActions("operator")).toBe(true);
    expect(canDecideActions("admin")).toBe(true);
    expect(canDecideActions("viewer")).toBe(false);
  });
});

describe("isExpired", () => {
  it("is false when there is no expiry", () => {
    expect(isExpired(null, NOW)).toBe(false);
  });

  it("is false before the expiry and true at or after it", () => {
    expect(isExpired("2026-10-14T10:05:00Z", NOW)).toBe(false);
    expect(isExpired("2026-10-14T10:00:00Z", NOW)).toBe(true);
    expect(isExpired("2026-10-14T09:00:00Z", NOW)).toBe(true);
  });

  it("treats an expiry it cannot read as expired", () => {
    expect(isExpired("not a date", NOW)).toBe(true);
  });
});

describe("expiryText", () => {
  it.each([
    ["2026-10-14T10:00:30Z", "Expires in under a minute"],
    ["2026-10-14T10:12:00Z", "Expires in 12 min"],
    [new Date(NOW + 3 * HOUR).toISOString(), "Expires in 3 h"],
    [new Date(NOW + DAY).toISOString(), "Expires in 1 day"],
    [new Date(NOW + 2 * DAY).toISOString(), "Expires in 2 days"],
    ["2026-10-14T09:59:00Z", "Expired"],
  ])("describes %s as %s", (expiresAt, text) => {
    expect(expiryText(expiresAt, NOW)).toBe(text);
  });
});

describe("decisionErrorMessage", () => {
  it("shows the fixed reload text for a 409", () => {
    expect(decisionErrorMessage(new ApiError(409, "stale hash"))).toBe(CHANGED_REQUEST_TEXT);
    expect(CHANGED_REQUEST_TEXT).toBe("This request changed or expired — reload the incident.");
  });

  it("shows the server detail for a 422", () => {
    expect(decisionErrorMessage(new ApiError(422, "comment is too long"))).toBe("comment is too long");
  });

  it("falls back to the general message for other errors", () => {
    expect(decisionErrorMessage(new ApiError(403, "csrf token missing or invalid"))).toBe(
      "csrf token missing or invalid",
    );
    expect(decisionErrorMessage(new Error("network down"))).toBe("network down");
  });
});
