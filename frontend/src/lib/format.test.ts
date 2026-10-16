import { describe, expect, it } from "vitest";
import { ApiError } from "../api/client";
import { absoluteTime, asSentence, errorMessage, percentFromFraction, percentFromHundred, relativeTime, withoutTitle } from "./format";

const NOW = new Date("2026-10-13T12:00:00Z");

function minutesBefore(minutes: number): string {
  return new Date(NOW.getTime() - minutes * 60_000).toISOString();
}

describe("relativeTime", () => {
  it.each([
    [30 * 1_000, "just now"],
    [12 * 60_000, "12 minutes ago"],
    [3 * 60 * 60_000, "3 hours ago"],
    [60 * 60_000, "1 hour ago"],
    [25 * 60 * 60_000, "1 day ago"],
    [50 * 60 * 60_000, "2 days ago"],
  ])("formats %i ms ago as %s", (elapsedMs, expected) => {
    const iso = new Date(NOW.getTime() - elapsedMs).toISOString();
    expect(relativeTime(iso, NOW)).toBe(expected);
  });

  it("treats a time in the future as just now", () => {
    expect(relativeTime(new Date(NOW.getTime() + 5 * 60_000).toISOString(), NOW)).toBe("just now");
  });

  it("returns the input when it is not a date", () => {
    expect(relativeTime("not a date", NOW)).toBe("not a date");
  });

  it("uses minutes for the first hour", () => {
    expect(relativeTime(minutesBefore(59), NOW)).toBe("59 minutes ago");
  });
});

describe("absoluteTime", () => {
  it("formats a valid time with the locale string", () => {
    const iso = "2026-10-13T12:00:00Z";
    expect(absoluteTime(iso)).toBe(new Date(iso).toLocaleString());
  });

  it("returns the input when it is not a date", () => {
    expect(absoluteTime("yesterday-ish")).toBe("yesterday-ish");
  });
});

describe("percent", () => {
  it("rounds a fraction between 0 and 1", () => {
    expect(percentFromFraction(0.923)).toBe("92%");
    expect(percentFromFraction(1)).toBe("100%");
  });

  it("rounds a value between 0 and 100", () => {
    expect(percentFromHundred(92.4)).toBe("92%");
    expect(percentFromHundred(7)).toBe("7%");
  });
});

describe("errorMessage", () => {
  it("asks for a new sign-in when the session ended", () => {
    expect(errorMessage(new ApiError(401, "nope"))).toBe("Your session ended. Sign in again.");
  });

  it("says when the thing is not found", () => {
    expect(errorMessage(new ApiError(404, "missing"))).toBe("Not found.");
  });

  it("uses the message of any other error", () => {
    expect(errorMessage(new Error("network down"))).toBe("network down");
    expect(errorMessage(new ApiError(500, "boom"))).toBe("boom");
  });

  it("falls back to a generic text for values that are not errors", () => {
    expect(errorMessage("<script>alert(1)</script>")).toBe("Request failed.");
  });
});

describe("asSentence", () => {
  it("capitalises and ends with a full stop once", () => {
    expect(asSentence("everything is running normally")).toBe("Everything is running normally.");
    expect(asSentence("The worker has never reported.")).toBe("The worker has never reported.");
    expect(asSentence("  ")).toBe("");
  });
});

describe("withoutTitle", () => {
  it("drops the repeated title from a server headline", () => {
    expect(withoutTitle("Disk full", "Disk full needs you: no safe fix is allowed.")).toBe("No safe fix is allowed.");
    expect(withoutTitle("Disk full", "Disk full: the problem went away on its own.")).toBe("The problem went away on its own.");
  });

  it("keeps a headline that does not start with the title", () => {
    expect(withoutTitle("Disk full", "something else")).toBe("Something else.");
  });
});
