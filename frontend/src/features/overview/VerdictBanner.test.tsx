import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { VerdictLevel } from "../../api/types";
import { VerdictBanner } from "./VerdictBanner";
import { HOSTILE_IMG } from "./testData";

const BOX_CLASSES: Record<VerdictLevel, string> = {
  ok: "bg-ok-soft",
  attention: "bg-warning-soft",
  degraded: "bg-warning-soft",
  down: "bg-critical-soft",
};

describe("VerdictBanner", () => {
  it.each<[VerdictLevel, string]>([
    ["ok", "All systems operational"],
    ["attention", "1 incident needs you"],
    ["degraded", "The LLM provider is degraded"],
    ["down", "The NOC is not working"],
  ])("shows the %s verdict sentence in a box for its tone", (level, sentence) => {
    render(<VerdictBanner verdict={{ level, sentence }} />);

    const banner = screen.getByRole("region", { name: "Overall status" });
    expect(screen.getByText(sentence)).toBeTruthy();
    expect(banner.className).toContain(BOX_CLASSES[level]);
  });

  it("shows hostile text as text, not as an element", () => {
    const { container } = render(<VerdictBanner verdict={{ level: "down", sentence: HOSTILE_IMG }} />);

    expect(screen.getByText(HOSTILE_IMG)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
