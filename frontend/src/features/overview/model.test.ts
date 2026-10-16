import { describe, expect, it } from "vitest";
import type { Role } from "../../api/types";
import {
  ACTIVITY_LIMIT,
  canCloseIncidents,
  recentActivity,
  serverLabel,
  serverTone,
} from "./model";
import { activityItem } from "./testData";

describe("server status", () => {
  it("maps each server status to a tone and a plain label", () => {
    expect(serverTone("up")).toBe("ok");
    expect(serverTone("down")).toBe("critical");
    expect(serverTone("unknown")).toBe("unknown");
    expect(serverLabel("up")).toBe("Up");
    expect(serverLabel("down")).toBe("Down");
    expect(serverLabel("unknown")).toBe("Unknown");
  });
});

describe("canCloseIncidents", () => {
  it.each<[Role, boolean]>([
    ["viewer", false],
    ["operator", true],
    ["admin", true],
  ])("allows %s: %s", (role, allowed) => {
    expect(canCloseIncidents(role)).toBe(allowed);
  });
});

describe("recentActivity", () => {
  it("keeps the newest entries up to the limit, in the order given", () => {
    const items = Array.from({ length: 20 }, (_, index) => activityItem({ text: `entry ${index}` }));

    const recent = recentActivity(items);

    expect(recent).toHaveLength(ACTIVITY_LIMIT);
    expect(recent[0]?.text).toBe("entry 0");
    expect(recent[ACTIVITY_LIMIT - 1]?.text).toBe(`entry ${ACTIVITY_LIMIT - 1}`);
  });
});

