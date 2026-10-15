import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { describe, expect, it } from "vitest";
import type { ActivityItem } from "../../api/types";
import { LiveActivity } from "./LiveActivity";
import { HOSTILE_IMG, activityItem } from "./testData";

function renderActivity(items: ActivityItem[]) {
  return render(
    <MemoryRouter>
      <LiveActivity items={items} />
    </MemoryRouter>,
  );
}

describe("LiveActivity", () => {
  it("shows the empty text when there is no activity", () => {
    renderActivity([]);

    expect(screen.getByText("No activity yet.")).toBeTruthy();
  });

  it("links an incident entry to its page and leaves an audit entry as plain text", () => {
    renderActivity([
      activityItem({ text: "Incident opened: DiskAlmostFull" }),
      activityItem({
        kind: "audit",
        text: "alice closed an incident",
        incident_id: null,
        actor: "alice",
      }),
    ]);

    const link = screen.getByRole("link", { name: "Incident opened: DiskAlmostFull" });
    expect(link.getAttribute("href")).toBe("/incidents/11111111-1111-1111-1111-111111111111");
    expect(screen.getByText("alice closed an incident").closest("a")).toBeNull();
    expect(screen.getAllByRole("link")).toHaveLength(1);
  });

  it("shows at most ten entries", () => {
    renderActivity(Array.from({ length: 20 }, (_, index) => activityItem({ text: `entry ${index}` })));

    expect(screen.getAllByRole("listitem")).toHaveLength(10);
  });

  it("shows hostile text as text and creates no element", () => {
    const { container } = renderActivity([activityItem({ text: HOSTILE_IMG, incident_id: null })]);

    expect(screen.getByText(HOSTILE_IMG)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
