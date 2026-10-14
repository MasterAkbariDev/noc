import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import {
  clampPercent,
  environmentTone,
  errorText,
  headlineWithoutIncidents,
  isAttention,
  isNotFound,
  openIncidentsText,
  serverStatusView,
  serviceView,
  UNREACHABLE_MESSAGE,
} from "./serverView";

describe("headlineWithoutIncidents", () => {
  it("drops the trailing open incidents phrase the server adds", () => {
    expect(headlineWithoutIncidents("Disk 92% full · 1 open incident", 1)).toBe("Disk 92% full");
    expect(headlineWithoutIncidents("Not reachable · 3 open incidents", 3)).toBe("Not reachable");
  });

  it("keeps the headline when it does not end with the phrase", () => {
    expect(headlineWithoutIncidents("Disk 92% full", 1)).toBe("Disk 92% full");
    expect(headlineWithoutIncidents("Disk 92% full · 2 open incidents", 1)).toBe(
      "Disk 92% full · 2 open incidents",
    );
  });

  it("returns an empty headline when the headline is only the phrase", () => {
    expect(headlineWithoutIncidents("1 open incident", 1)).toBe("");
  });
});

describe("serverStatusView", () => {
  it.each([
    ["up", "Reachable", "ok"],
    ["down", "Not reachable", "critical"],
    ["unknown", "Unknown", "unknown"],
  ] as const)("maps %s to %s with the %s tone", (status, label, tone) => {
    expect(serverStatusView(status)).toEqual({ label, tone });
  });
});

describe("serviceView", () => {
  it("maps the three service states to text and tone", () => {
    expect(serviceView(true)).toEqual({ label: "Up", tone: "ok" });
    expect(serviceView(false)).toEqual({ label: "Down", tone: "critical" });
    expect(serviceView(null)).toEqual({ label: "Unknown", tone: "unknown" });
  });
});

describe("environmentTone", () => {
  it("only prod stands out", () => {
    expect(environmentTone("prod")).toBe("warning");
    expect(environmentTone("staging")).toBe("neutral");
  });
});

describe("percent helpers", () => {
  it("flags values at or above the attention threshold", () => {
    expect(isAttention(89.9)).toBe(false);
    expect(isAttention(90)).toBe(true);
  });

  it("keeps a bar width between 0 and 100", () => {
    expect(clampPercent(-4)).toBe(0);
    expect(clampPercent(130)).toBe(100);
    expect(clampPercent(37)).toBe(37);
  });
});

describe("openIncidentsText", () => {
  it.each([
    [0, "No open incidents"],
    [1, "1 open incident"],
    [3, "3 open incidents"],
  ])("reads %i as %s", (count, text) => {
    expect(openIncidentsText(count)).toBe(text);
  });
});

describe("error helpers", () => {
  it("shows the API detail for an API error and a fixed text otherwise", () => {
    expect(errorText(new ApiError(500, "database is busy"))).toBe("database is busy");
    expect(errorText(new TypeError("Failed to fetch"))).toBe(UNREACHABLE_MESSAGE);
  });

  it("recognises only a 404 as not found", () => {
    expect(isNotFound(new ApiError(404, "not found"))).toBe(true);
    expect(isNotFound(new ApiError(500, "boom"))).toBe(false);
    expect(isNotFound(new Error("network"))).toBe(false);
  });
});
