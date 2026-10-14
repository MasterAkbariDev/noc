import { describe, expect, it } from "vitest";
import { NO_FILTERS } from "./filters";
import { chainView, emptyFeedText } from "./view";

describe("chainView", () => {
  it("reports an intact chain as ok", () => {
    expect(chainView({ ok: true, broken_at: null })).toEqual({ label: "Audit log intact", tone: "ok" });
  });

  it("names the entry where the chain breaks", () => {
    expect(chainView({ ok: false, broken_at: 17 })).toEqual({
      label: "Audit log broken at entry 17",
      tone: "critical",
    });
  });

  it("reports a broken chain without an entry when none is named", () => {
    expect(chainView({ ok: false, broken_at: null })).toEqual({ label: "Audit log broken", tone: "critical" });
  });
});

describe("emptyFeedText", () => {
  it("says there is no activity when no filter is set", () => {
    expect(emptyFeedText(NO_FILTERS)).toBe("No activity yet.");
  });

  it("says nothing matches when a filter is set", () => {
    expect(emptyFeedText({ action: "login", actor: "" })).toBe("No activity matches these filters.");
    expect(emptyFeedText({ action: "", actor: "bob" })).toBe("No activity matches these filters.");
  });
});
