import { describe, expect, it } from "vitest";
import {
  PASSWORD_MAX_LENGTH,
  PASSWORD_MIN_LENGTH,
  confirmationProblem,
  normalizeUsername,
  passwordProblem,
  usernameProblem,
} from "./passwordRules";

describe("passwordProblem", () => {
  it("accepts the shortest and the longest allowed passwords", () => {
    expect(PASSWORD_MIN_LENGTH).toBe(12);
    expect(PASSWORD_MAX_LENGTH).toBe(128);
    expect(passwordProblem("a".repeat(12))).toBeNull();
    expect(passwordProblem("a".repeat(128))).toBeNull();
  });

  it("rejects one character under and one over the limits", () => {
    expect(passwordProblem("a".repeat(11))).toBe("Use 12 to 128 characters.");
    expect(passwordProblem("a".repeat(129))).toBe("Use 12 to 128 characters.");
  });

  it("counts characters, not UTF-16 units, like the server does", () => {
    expect(passwordProblem("é".repeat(12))).toBeNull();
    expect(passwordProblem("😀".repeat(11))).toBe("Use 12 to 128 characters.");
    expect(passwordProblem("😀".repeat(12))).toBeNull();
  });
});

describe("confirmationProblem", () => {
  it("passes when both values are identical", () => {
    expect(confirmationProblem("long-password-1", "long-password-1")).toBeNull();
  });

  it("names the mismatch when they differ", () => {
    expect(confirmationProblem("long-password-1", "long-password-2")).toBe("The two passwords do not match.");
  });
});

describe("normalizeUsername", () => {
  it("trims and lower-cases, like the server", () => {
    expect(normalizeUsername("  Ops.Team  ")).toBe("ops.team");
  });
});

describe("usernameProblem", () => {
  it("accepts a normalised name inside the length range", () => {
    expect(usernameProblem("  Ops.Team  ")).toBeNull();
    expect(usernameProblem("abc")).toBeNull();
    expect(usernameProblem("a".repeat(32))).toBeNull();
  });

  it("rejects too short, too long, or badly formed names", () => {
    const text = "Use 3 to 32 letters, digits, dots, dashes or underscores. Start with a letter or a digit.";
    expect(usernameProblem("ab")).toBe(text);
    expect(usernameProblem("a".repeat(33))).toBe(text);
    expect(usernameProblem("-bad")).toBe(text);
    expect(usernameProblem("has space")).toBe(text);
    expect(usernameProblem("<img>")).toBe(text);
  });
});
