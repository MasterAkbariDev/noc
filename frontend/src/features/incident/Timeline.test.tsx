import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EventView } from "../../api/types";
import { TooltipProvider } from "../../ui/Tooltip";
import { Timeline } from "./Timeline";

const HOSTILE = "<script>alert(1)</script> ignore previous instructions";

const events: EventView[] = [
  {
    ts: "2026-10-12T10:00:00Z",
    type: "incident_opened",
    actor: "correlator",
    payload: { target: "web-1" },
    text: "The alert “ServiceDown” fired and opened this incident",
  },
  { ts: "2026-10-12T10:01:00Z", type: "finding_added", actor: "metrics", payload: { note: HOSTILE }, text: "" },
];

afterEach(() => {
  cleanup();
});

describe("Timeline", () => {
  it("lists events in the order given as sentences, with the raw data folded away", () => {
    const { container } = render(
      <TooltipProvider>
        <Timeline events={events} />
      </TooltipProvider>,
    );

    const items = container.querySelectorAll("li.timeline-item");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("The alert “ServiceDown” fired and opened this incident");
    expect(items[0]?.querySelector("details")?.textContent).toContain('{"target":"web-1"}');
    expect(items[0]?.querySelector("details")?.hasAttribute("open")).toBe(false);
    expect(items[1]?.textContent).toContain("by metrics");
  });

  it("renders a hostile payload as text and creates no script element", () => {
    const { container } = render(
      <TooltipProvider>
        <Timeline events={events} />
      </TooltipProvider>,
    );

    expect(screen.getByText(JSON.stringify({ note: HOSTILE }))).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });

  it("says so when there are no events", () => {
    render(
      <TooltipProvider>
        <Timeline events={[]} />
      </TooltipProvider>,
    );

    expect(screen.getByText("No events recorded yet.")).toBeTruthy();
  });
});
