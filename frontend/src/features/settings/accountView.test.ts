import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/client";
import { NETWORK_FAILURE_TEXT, accountStatusView, parseRole, roleLabel, settingsErrorText } from "./accountView";

describe("parseRole", () => {
  it("accepts the three roles and nothing else", () => {
    expect(parseRole("viewer")).toBe("viewer");
    expect(parseRole("operator")).toBe("operator");
    expect(parseRole("admin")).toBe("admin");
    expect(parseRole("root")).toBeNull();
    expect(parseRole("")).toBeNull();
  });
});

describe("roleLabel", () => {
  it("writes each role as a plain word", () => {
    expect(roleLabel("viewer")).toBe("Viewer");
    expect(roleLabel("operator")).toBe("Operator");
    expect(roleLabel("admin")).toBe("Admin");
  });
});

describe("accountStatusView", () => {
  it("shows an active account as ok and a disabled one as critical, always with text", () => {
    expect(accountStatusView(false)).toEqual({ label: "Active", tone: "ok" });
    expect(accountStatusView(true)).toEqual({ label: "Disabled", tone: "critical" });
  });
});

describe("settingsErrorText", () => {
  it("shows the server detail for an API error", () => {
    expect(settingsErrorText(new ApiError(409, "username already exists"))).toBe("username already exists");
  });

  it("says the NOC could not be reached for any other failure", () => {
    expect(settingsErrorText(new TypeError("Failed to fetch"))).toBe(NETWORK_FAILURE_TEXT);
  });
});
