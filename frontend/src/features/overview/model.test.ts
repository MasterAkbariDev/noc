import { describe, expect, it } from "vitest";
import type { Kpis, Role, VerdictLevel } from "../../api/types";
import { ACTIVITY_LIMIT, canCloseIncidents, kpiViews, recentActivity, serverLabel, serverTone, verdictTone } from "./model";
import { activityItem } from "./testData";

const HEALTHY_KPIS: Kpis = {
  open_incidents: 0,
  needs_you: 0,
  servers_up: 2,
  servers_total: 2,
  llm_keys_ok: 10,
  llm_keys_total: 10,
};

describe("verdictTone", () => {
  it.each<[VerdictLevel, string]>([
    ["ok", "ok"],
    ["attention", "warning"],
    ["degraded", "warning"],
    ["down", "critical"],
  ])("maps the %s level to the %s tone", (level, tone) => {
    expect(verdictTone(level)).toBe(tone);
  });
});

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
  it("keeps the newest fifteen entries in the order given", () => {
    const items = Array.from({ length: 20 }, (_, index) => activityItem({ text: `entry ${index}` }));

    const recent = recentActivity(items);

    expect(recent).toHaveLength(ACTIVITY_LIMIT);
    expect(recent[0]?.text).toBe("entry 0");
    expect(recent[ACTIVITY_LIMIT - 1]?.text).toBe("entry 14");
  });
});

describe("kpiViews", () => {
  it("links each tile to its page", () => {
    expect(kpiViews(HEALTHY_KPIS).map((view) => view.to)).toEqual([
      "/incidents?filter=open",
      "/incidents?filter=needs-you",
      "/servers",
      "/system",
    ]);
  });

  it("is healthy when nothing needs the operator and every server and key works", () => {
    expect(kpiViews(HEALTHY_KPIS).map((view) => view.tone)).toEqual(["neutral", "ok", "ok", "ok"]);
  });

  it("warns on the needs-you tile and on partly working keys or servers", () => {
    const views = kpiViews({
      ...HEALTHY_KPIS,
      needs_you: 1,
      servers_up: 1,
      llm_keys_ok: 9,
    });

    expect(views[1]?.value).toBe("1");
    expect(views[1]?.tone).toBe("warning");
    expect(views[2]?.value).toBe("1/2");
    expect(views[2]?.tone).toBe("warning");
    expect(views[3]?.value).toBe("9/10");
    expect(views[3]?.tone).toBe("warning");
  });

  it("does not warn about servers or keys when there are none", () => {
    const views = kpiViews({ ...HEALTHY_KPIS, servers_up: 0, servers_total: 0, llm_keys_ok: 0, llm_keys_total: 0 });

    expect(views[2]?.tone).toBe("neutral");
    expect(views[3]?.tone).toBe("neutral");
  });

  it("says Replay mode instead of 0/0 on the LLM tile when the LLM replays recorded answers", () => {
    const views = kpiViews({ ...HEALTHY_KPIS, llm_keys_ok: 0, llm_keys_total: 0 }, "replay");

    expect(views[3]).toEqual({
      key: "llm",
      label: "LLM keys",
      value: "Replay mode",
      hint: "recorded answers",
      tone: "neutral",
      to: "/system",
    });
  });

  it("keeps the key count when the mode is live or not known yet", () => {
    expect(kpiViews(HEALTHY_KPIS, "live")[3]?.value).toBe("10/10");
    expect(kpiViews(HEALTHY_KPIS)[3]?.value).toBe("10/10");
  });
});
