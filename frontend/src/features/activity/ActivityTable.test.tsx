import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { TooltipProvider } from "../../ui/Tooltip";
import { ActivityTable } from "./ActivityTable";
import { HOSTILE_TEXT, entryFixture } from "./fixtures";

function renderTable(entries: ReturnType<typeof entryFixture>[], emptyText = "No activity yet.") {
  return render(
    <TooltipProvider>
      <ActivityTable entries={entries} emptyText={emptyText} />
    </TooltipProvider>,
  );
}

afterEach(() => {
  cleanup();
});

describe("ActivityTable", () => {
  it("shows the actor, the plain action label and the summary for each row", () => {
    renderTable([entryFixture()]);

    expect(screen.getByRole("columnheader", { name: "Who" })).toBeTruthy();
    expect(screen.getByText("alice")).toBeTruthy();
    expect(screen.getByText("Incident closed")).toBeTruthy();
    expect(screen.getByText("alice closed incident 3f2a")).toBeTruthy();
  });

  it("keeps the raw action code in a term that shows it on focus", async () => {
    renderTable([entryFixture()]);

    fireEvent.focus(screen.getByText("Incident closed"));

    expect((await screen.findAllByText("incident_closed")).length).toBeGreaterThan(0);
  });

  it("shows the payload as JSON text only after the row is expanded", () => {
    renderTable([entryFixture()]);

    expect(screen.queryByText(/"incident_id"/)).toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "Show details" }));

    expect(screen.getByText(/"incident_id": "3f2a"/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Hide details" }).getAttribute("aria-expanded")).toBe("true");
  });

  it("shows hostile actor, summary and payload as text and creates no element", () => {
    const { container } = renderTable([
      entryFixture({
        actor: HOSTILE_TEXT,
        summary: HOSTILE_TEXT,
        payload: { note: HOSTILE_TEXT },
      }),
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Show details" }));

    expect(screen.getAllByText(HOSTILE_TEXT, { exact: false }).length).toBeGreaterThan(0);
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("shows the empty text when there are no rows", () => {
    renderTable([], "No activity matches these filters.");

    expect(screen.getByText("No activity matches these filters.")).toBeTruthy();
  });
});
