import { describe, expect, it } from "vitest";
import {
  ACTOR_MAX_LENGTH,
  ACTIVITY_PAGE_SIZE,
  activityQuery,
  activitySearchParams,
  isKnownAction,
  parseActivityFilters,
} from "./filters";

describe("parseActivityFilters", () => {
  it("reads a known action and a trimmed actor from the URL", () => {
    const params = new URLSearchParams("action=login&actor=%20alice%20");

    expect(parseActivityFilters(params)).toEqual({ action: "login", actor: "alice" });
  });

  it("drops an action that is not a known label", () => {
    const params = new URLSearchParams("action=constructor");

    expect(parseActivityFilters(params)).toEqual({ action: "", actor: "" });
  });

  it("limits the actor to the username length", () => {
    const params = new URLSearchParams({ actor: "x".repeat(ACTOR_MAX_LENGTH + 10) });

    expect(parseActivityFilters(params).actor).toHaveLength(ACTOR_MAX_LENGTH);
  });
});

describe("activitySearchParams", () => {
  it("writes only the filters that are set", () => {
    expect(activitySearchParams({ action: "", actor: "" }).toString()).toBe("");
    expect(activitySearchParams({ action: "login", actor: "" }).toString()).toBe("action=login");
    expect(activitySearchParams({ action: "", actor: "bob" }).toString()).toBe("actor=bob");
  });
});

describe("activityQuery", () => {
  it("asks for one page and leaves out the empty filters", () => {
    expect(activityQuery({ action: "", actor: "" }, undefined)).toEqual({
      limit: ACTIVITY_PAGE_SIZE,
      before_id: undefined,
      action: undefined,
      actor: undefined,
    });
  });

  it("passes the filters and the paging cursor through", () => {
    expect(activityQuery({ action: "login_failed", actor: "bob" }, 42)).toEqual({
      limit: ACTIVITY_PAGE_SIZE,
      before_id: 42,
      action: "login_failed",
      actor: "bob",
    });
  });
});

describe("isKnownAction", () => {
  it("accepts the labelled actions and nothing else", () => {
    expect(isKnownAction("incident_closed")).toBe(true);
    expect(isKnownAction("incident")).toBe(false);
    expect(isKnownAction("")).toBe(false);
  });
});
