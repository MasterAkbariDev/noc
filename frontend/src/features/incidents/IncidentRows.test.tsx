import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import type { IncidentSummary } from "../../api/types";
import { TooltipProvider } from "../../ui";
import { IncidentRows } from "./IncidentRows";

const UNTRUSTED_TITLE = '<script>document.title = "pwned"</script>Disk full';

const incidents: IncidentSummary[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    title: "Service down on web-1",
    status: "ESCALATED",
    severity: "critical",
    target: "web-1",
    opened_at: "2026-10-12T10:00:00Z",
    root_cause_code: "service_crashed",
    confidence: 0.82,
    escalation_reason: "no_allowed_action",
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    title: UNTRUSTED_TITLE,
    status: "NEW",
    severity: "warning",
    target: "db-1",
    opened_at: "2026-10-12T11:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
  },
];

function renderRows(rows: IncidentSummary[], emptyText = "Nothing here.") {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <TooltipProvider>
          <IncidentRows incidents={rows} emptyText={emptyText} />
        </TooltipProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("IncidentRows", () => {
  it("renders one body row per incident with a link to its detail page", () => {
    renderRows(incidents);

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(incidents.length + 1);

    const link = screen.getByRole("link", { name: "Service down on web-1" });
    expect(link.getAttribute("href")).toBe(
      "/incidents/11111111-1111-1111-1111-111111111111",
    );
  });

  it("shows the plain status label and the severity text in each row", () => {
    renderRows(incidents);

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(within(rows[1]!).getByText("Needs you")).toBeTruthy();
    expect(within(rows[1]!).getByText("Critical")).toBeTruthy();
    expect(within(rows[2]!).getByText("New")).toBeTruthy();
    expect(within(rows[2]!).getByText("Warning")).toBeTruthy();
  });

  it("shows the humanised root cause with its confidence and the raw code on focus", async () => {
    renderRows(incidents);

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    const cause = within(rows[1]!).getByText("Service crashed");
    expect(within(rows[1]!).getByText(/82% confidence/)).toBeTruthy();
    expect(within(rows[2]!).getByText("Not diagnosed yet")).toBeTruthy();

    fireEvent.focus(cause);

    expect(
      (await screen.findAllByText("service_crashed")).length,
    ).toBeGreaterThan(0);
  });

  it("shows the target and the relative opened time with the full time in its title", () => {
    const { container } = renderRows(incidents);

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(within(rows[2]!).getByText("db-1")).toBeTruthy();
    const opened = container.querySelector("time");
    expect(opened?.getAttribute("datetime")).toBe("2026-10-12T10:00:00Z");
    expect(opened?.getAttribute("title")).toBe(
      new Date("2026-10-12T10:00:00Z").toLocaleString(),
    );
  });

  it("shows hostile title text as plain text and creates no script element", () => {
    const { container } = renderRows(incidents);

    expect(screen.getByText(UNTRUSTED_TITLE)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
    expect(document.title).not.toBe("pwned");
  });

  it("shows the empty text in a single row when there are no incidents", () => {
    renderRows([], "No open incidents. All quiet.");

    expect(screen.getByText("No open incidents. All quiet.")).toBeTruthy();
  });
});
