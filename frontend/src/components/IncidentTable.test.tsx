import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router";
import type { IncidentSummary } from "../api/types";
import { IncidentTable } from "./IncidentTable";

const UNTRUSTED_TITLE = '<script>document.title = "pwned"</script>Disk full';

const incidents: IncidentSummary[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    title: "Service down on web-1",
    status: "ESCALATED",
    severity: "critical",
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
    opened_at: "2026-10-12T11:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
  },
];

afterEach(() => {
  cleanup();
});

function renderTable(rows: IncidentSummary[]) {
  return render(
    <MemoryRouter>
      <IncidentTable incidents={rows} />
    </MemoryRouter>,
  );
}

describe("IncidentTable", () => {
  it("renders one body row per incident with a link to its detail page", () => {
    renderTable(incidents);

    const rows = within(screen.getByRole("table")).getAllByRole("row");
    expect(rows).toHaveLength(incidents.length + 1);

    const link = screen.getByRole("link", { name: "Service down on web-1" });
    expect(link.getAttribute("href")).toBe("/incidents/11111111-1111-1111-1111-111111111111");
    expect(within(rows[1]!).getByText("ESCALATED")).toBeTruthy();
    expect(within(rows[1]!).getByText("0.82")).toBeTruthy();
  });

  it("shows untrusted text containing a script tag as plain text", () => {
    const { container } = renderTable(incidents);

    expect(screen.getByText(UNTRUSTED_TITLE)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
    expect(document.title).not.toBe("pwned");
  });

  it("says so when there are no incidents", () => {
    renderTable([]);

    expect(screen.getByText("No incidents match this filter.")).toBeTruthy();
  });
});
