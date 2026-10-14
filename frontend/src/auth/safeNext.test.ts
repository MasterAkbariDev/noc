import { describe, expect, it } from "vitest";
import { safeNext } from "./safeNext";

describe("safeNext", () => {
  it.each<[string | null, string]>([
    ["/incidents", "/incidents"],
    ["/incidents?status=NEW", "/incidents?status=NEW"],
    ["/servers/web-1", "/servers/web-1"],
    [null, "/"],
    ["", "/"],
    ["incidents", "/"],
    ["//evil.com", "/"],
    ["https://evil.com", "/"],
    ["/\\evil.com", "/"],
    ["/\t/evil.com", "/"],
    ["/\n/evil.com", "/"],
    ["javascript:alert(1)", "/"],
  ])("maps %j to %j", (value, expected) => {
    expect(safeNext(value)).toBe(expected);
  });
});
