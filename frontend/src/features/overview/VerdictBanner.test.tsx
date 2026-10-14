import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import type { OverviewLevel } from "../../lib/tones";
import { VerdictBanner } from "./VerdictBanner";
import { HOSTILE_IMG } from "./testData";

const BOX_CLASSES: Record<OverviewLevel, string> = {
  ok: "bg-ok-soft",
  working: "bg-info-soft",
  attention: "bg-warning-soft",
  degraded: "bg-warning-soft",
  down: "bg-critical-soft",
};

function renderBanner(level: OverviewLevel, sentence: string) {
  return render(
    <MemoryRouter>
      <VerdictBanner verdict={{ level, sentence }} />
    </MemoryRouter>,
  );
}

describe("VerdictBanner", () => {
  it.each<[OverviewLevel, string]>([
    ["ok", "2 servers · 0 open incidents · LLM OK"],
    ["working", "Working on 1 incident · 2 servers up · LLM OK"],
    ["attention", "1 incident needs you"],
    ["degraded", "The LLM provider is degraded"],
    ["down", "The NOC is not working"],
  ])("shows the %s verdict sentence in a box for its tone", (level, sentence) => {
    renderBanner(level, sentence);

    const banner = screen.getByRole("region", { name: "Overall status" });
    expect(screen.getByText(sentence)).toBeTruthy();
    expect(banner.className).toContain(BOX_CLASSES[level]);
  });

  it.each<OverviewLevel>(["attention", "degraded", "down"])(
    "links the %s banner to the system health page",
    (level) => {
      renderBanner(level, "Something needs a look");

      const link = screen.getByRole("link", { name: "See system health" });
      expect(link.getAttribute("href")).toBe("/system");
    },
  );

  it.each<OverviewLevel>(["ok", "working"])("offers no system health link for %s", (level) => {
    renderBanner(level, "Something is fine");

    expect(screen.queryByRole("link")).toBeNull();
  });

  it("puts the NOC problem on its own line when incidents need a person", () => {
    renderBanner("attention", "1 incident needs you · Worker: Last heartbeat 6 min ago");

    expect(screen.getByText("1 incident needs you")).toBeTruthy();
    expect(screen.getByText("Worker: Last heartbeat 6 min ago")).toBeTruthy();
  });

  it("shows hostile text as text, not as an element", () => {
    const { container } = renderBanner("down", HOSTILE_IMG);

    expect(screen.getByText(HOSTILE_IMG)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
