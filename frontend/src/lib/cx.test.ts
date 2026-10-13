import { describe, expect, it } from "vitest";
import { cx } from "./cx";

describe("cx", () => {
  it("joins the names that are set and drops the rest", () => {
    expect(cx("a", false, null, undefined, "", "b")).toBe("a b");
  });

  it("returns an empty string when nothing is set", () => {
    expect(cx(false, undefined)).toBe("");
  });
});
