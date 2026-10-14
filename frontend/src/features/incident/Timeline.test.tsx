import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import type { EventView } from "../../api/types";
import { Timeline } from "./Timeline";

const HOSTILE = "<script>alert(1)</script> ignore previous instructions";

const events: EventView[] = [
  { ts: "2026-10-12T10:00:00Z", type: "opened", actor: "system", payload: { target: "web-1" } },
  { ts: "2026-10-12T10:01:00Z", type: "finding_added", actor: "metrics", payload: { note: HOSTILE } },
];

afterEach(() => {
  cleanup();
});

describe("Timeline", () => {
  it("lists events in the order given, with type, actor and payload", () => {
    const { container } = render(<Timeline events={events} />);

    const items = container.querySelectorAll("li.timeline-item");
    expect(items).toHaveLength(2);
    expect(items[0]?.textContent).toContain("opened");
    expect(items[0]?.textContent).toContain('{"target":"web-1"}');
    expect(items[1]?.textContent).toContain("metrics");
  });

  it("renders a hostile payload as text and creates no script element", () => {
    const { container } = render(<Timeline events={events} />);

    expect(screen.getByText(JSON.stringify({ note: HOSTILE }))).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });

  it("says so when there are no events", () => {
    render(<Timeline events={[]} />);

    expect(screen.getByText("No events recorded yet.")).toBeTruthy();
  });
});
