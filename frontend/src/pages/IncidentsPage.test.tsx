import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import type { IncidentSummary } from "../api/types";
import { TooltipProvider } from "../ui";
import { IncidentsPage } from "./IncidentsPage";

const fetchMock = vi.fn<typeof fetch>();

const UNTRUSTED_TITLE = '<img src=x onerror="alert(1)">Disk full';

function incident(overrides: Partial<IncidentSummary> & Pick<IncidentSummary, "id" | "title" | "status">): IncidentSummary {
  return {
    severity: "warning",
    target: "web-1",
    opened_at: "2026-10-12T10:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
    ...overrides,
  };
}

const openRow = incident({ id: "a", title: "Disk almost full", status: "NEW", target: "web-1" });
const escalatedRow = incident({
  id: "b",
  title: "Service down",
  status: "ESCALATED",
  severity: "critical",
  target: "web-1",
  root_cause_code: "service_crashed",
  confidence: 0.82,
});
const resolvedRow = incident({ id: "c", title: "Backup late", status: "RESOLVED", severity: "info", target: "backup-1" });
const approvalRow = incident({
  id: "d",
  title: "Restore approval",
  status: "AWAITING_APPROVAL",
  severity: "critical",
  target: "db-1",
});

const ALL_ROWS = [openRow, escalatedRow, resolvedRow, approvalRow];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function answer(rows: IncidentSummary[], path: string): IncidentSummary[] {
  const url = new URL(path, "http://noc.test");
  const statuses = url.searchParams.getAll("statuses");
  const needle = (url.searchParams.get("q") ?? "").trim().toLowerCase();
  return rows.filter(
    (row) =>
      (statuses.length === 0 || statuses.includes(row.status)) &&
      (needle === "" || row.title.toLowerCase().includes(needle) || row.target.toLowerCase().includes(needle)),
  );
}

function serve(rows: IncidentSummary[], servers: { name: string }[] = []) {
  fetchMock.mockImplementation(async (input) => {
    const path = String(input);
    if (path.startsWith("/api/servers")) {
      return jsonResponse(servers);
    }
    return jsonResponse(answer(rows, path));
  });
}

function requestedUrls(): URL[] {
  return fetchMock.mock.calls
    .map(([input]) => new URL(String(input), "http://noc.test"))
    .filter((url) => url.pathname.startsWith("/api/incidents"));
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function currentLocation(): string {
  return screen.getByTestId("location").textContent ?? "";
}

function renderList(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route
              path="/incidents"
              element={
                <>
                  <IncidentsPage />
                  <LocationProbe />
                </>
              }
            />
          </Routes>
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function titlesShown(): string[] {
  const table = screen.getByRole("table");
  return within(table)
    .queryAllByRole("link")
    .map((link) => link.textContent ?? "");
}

beforeEach(() => {
  serve(ALL_ROWS);
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("IncidentsPage", () => {
  it("asks the server for up to 200 open incidents and shows them by default", async () => {
    renderList("/incidents");

    expect(await screen.findByRole("link", { name: "Disk almost full" })).toBeTruthy();
    const first = requestedUrls()[0];
    expect(first?.pathname).toBe("/api/incidents");
    expect(first?.searchParams.get("limit")).toBe("200");
    expect(first?.searchParams.getAll("statuses")).toContain("ESCALATED");
    expect(first?.searchParams.getAll("statuses")).not.toContain("RESOLVED");
    expect(first?.searchParams.has("q")).toBe(false);
    expect(titlesShown()).toEqual(["Disk almost full", "Service down", "Restore approval"]);
    expect(screen.getByRole("button", { name: "Open" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("sends the statuses of the chosen chip and no status filter for All", async () => {
    renderList("/incidents?filter=needs-you");
    await screen.findByRole("link", { name: "Service down" });

    expect(requestedUrls().at(-1)?.searchParams.getAll("statuses")).toEqual(["ESCALATED", "AWAITING_APPROVAL"]);

    fireEvent.click(screen.getByRole("button", { name: "All" }));

    await waitFor(() => expect(requestedUrls().at(-1)?.searchParams.has("statuses")).toBe(false));
  });

  it("waits for the search to settle before asking the server, so each keystroke is not a request", async () => {
    renderList("/incidents?filter=all");
    await screen.findByRole("link", { name: "Backup late" });

    const search = screen.getByRole("searchbox", { name: "Search" });
    fireEvent.change(search, { target: { value: "d" } });
    fireEvent.change(search, { target: { value: "db-1" } });

    await waitFor(() => expect(titlesShown()).toEqual(["Restore approval"]));
    const searches = requestedUrls().map((url) => url.searchParams.get("q"));
    expect(searches).not.toContain("d");
    expect(searches.at(-1)).toBe("db-1");
  });

  it("falls back to the open filter for an unknown filter in the URL", async () => {
    renderList("/incidents?filter=bogus");

    await screen.findByRole("link", { name: "Disk almost full" });
    expect(screen.getByRole("button", { name: "Open" }).getAttribute("aria-pressed")).toBe("true");
  });

  it("shows only the incidents that need you when that chip is chosen, and records it in the URL", async () => {
    renderList("/incidents");
    await screen.findByRole("link", { name: "Disk almost full" });

    fireEvent.click(screen.getByRole("button", { name: "Needs you" }));

    await waitFor(() => expect(currentLocation()).toBe("/incidents?filter=needs-you"));
    await waitFor(() => expect(titlesShown()).toEqual(["Service down", "Restore approval"]));
  });

  it("shows the resolved incidents for the resolved chip and everything for all", async () => {
    renderList("/incidents?filter=resolved");

    expect(await screen.findByRole("link", { name: "Backup late" })).toBeTruthy();
    expect(titlesShown()).toEqual(["Backup late"]);

    fireEvent.click(screen.getByRole("button", { name: "All" }));

    await waitFor(() => expect(titlesShown()).toHaveLength(ALL_ROWS.length));
    expect(currentLocation()).toBe("/incidents?filter=all");
  });

  it("filters the rows by the search text on title or target and records it in the URL", async () => {
    renderList("/incidents?filter=all");
    await screen.findByRole("link", { name: "Backup late" });

    fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), { target: { value: "db-1" } });

    await waitFor(() => expect(currentLocation()).toBe("/incidents?filter=all&q=db-1"));
    await waitFor(() => expect(titlesShown()).toEqual(["Restore approval"]));
  });

  it("filters the rows by the severity named in the URL", async () => {
    renderList("/incidents?severity=critical");

    expect(await screen.findByRole("link", { name: "Service down" })).toBeTruthy();
    expect(titlesShown()).toEqual(["Service down", "Restore approval"]);
    expect((screen.getByLabelText("Severity") as HTMLSelectElement).value).toBe("critical");
  });

  it("writes the chosen severity to the URL and clears it for All severities", async () => {
    renderList("/incidents");
    await screen.findByRole("link", { name: "Disk almost full" });

    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "critical" } });
    await waitFor(() => expect(currentLocation()).toBe("/incidents?severity=critical"));

    fireEvent.change(screen.getByLabelText("Severity"), { target: { value: "" } });
    await waitFor(() => expect(currentLocation()).toBe("/incidents"));
  });

  it("says the open list is quiet when nothing is open", async () => {
    serve([resolvedRow]);
    renderList("/incidents");

    expect(await screen.findByText("No open incidents. All quiet.")).toBeTruthy();
  });

  it("says no incidents match when the search finds nothing in the chosen filter", async () => {
    renderList("/incidents?filter=needs-you");

    await screen.findByRole("link", { name: "Service down" });
    fireEvent.change(screen.getByRole("searchbox", { name: "Search" }), { target: { value: "zzz" } });

    expect(await screen.findByText("No incidents match these filters.")).toBeTruthy();
  });

  it("lists every known server in the server filter, even one without incidents", async () => {
    serve([openRow], [{ name: "web-1" }, { name: "db-2" }]);
    renderList("/incidents");

    expect(await screen.findByText("Disk almost full")).toBeTruthy();
    expect(screen.getByRole("option", { name: "db-2" })).toBeTruthy();
    expect(screen.getByRole("option", { name: "web-1" })).toBeTruthy();
  });

  it("explains an empty chip when the server has no incident for it", async () => {
    serve([openRow]);
    renderList("/incidents?filter=resolved");

    expect(await screen.findByText("No resolved incidents.")).toBeTruthy();
  });

  it("says nothing needs you when no incident is escalated or waiting", async () => {
    serve([openRow]);
    renderList("/incidents?filter=needs-you");

    expect(await screen.findByText("Nothing needs you right now.")).toBeTruthy();
  });

  it("shows a hostile title as plain text and creates no element", async () => {
    serve([incident({ id: "x", title: UNTRUSTED_TITLE, status: "NEW" })]);
    const { container } = renderList("/incidents");

    expect(await screen.findByText(UNTRUSTED_TITLE)).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows the error with the server's detail and retries on Try again", async () => {
    fetchMock.mockResolvedValueOnce(jsonResponse({ detail: "database unavailable" }, 500));
    renderList("/incidents");

    expect(await screen.findByText("database unavailable")).toBeTruthy();
    expect(screen.getByRole("alert").textContent).toContain("Incidents did not load");

    serve(ALL_ROWS);
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("link", { name: "Disk almost full" })).toBeTruthy();
  });
});
