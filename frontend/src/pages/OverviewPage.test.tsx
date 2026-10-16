import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { getFleetLive, getLlmStatus, getMetrics, getOverview, getSystemHealth, listIncidents } from "../api/client";
import type { FleetLive, LlmStatus, Role } from "../api/types";
import { fixedItem, metricsFixture, overviewFixture, serverSummary, systemHealthFixture } from "../features/overview/testData";
import { OverviewPage } from "./OverviewPage";

const session = vi.hoisted(() => ({ role: "operator" as Role }));

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getOverview: vi.fn(),
  getLlmStatus: vi.fn(),
  getMetrics: vi.fn(),
  getSystemHealth: vi.fn(),
  listIncidents: vi.fn(),
  getFleetLive: vi.fn(),
}));

function llmStatus(mode: LlmStatus["mode"]): LlmStatus {
  return { mode, keys: [] };
}

vi.mock("../auth/session", () => ({
  useSession: () => ({
    status: "authenticated",
    me: { username: "alice", role: session.role, via: "session" },
    login: vi.fn(),
    logout: vi.fn(),
  }),
}));

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <OverviewPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  session.role = "operator";
  vi.mocked(getOverview).mockReset();
  vi.mocked(getLlmStatus).mockReset();
  vi.mocked(getLlmStatus).mockResolvedValue(llmStatus("live"));
  vi.mocked(getMetrics).mockReset();
  vi.mocked(getMetrics).mockResolvedValue(metricsFixture());
  vi.mocked(getSystemHealth).mockReset();
  vi.mocked(getSystemHealth).mockResolvedValue(systemHealthFixture());
  vi.mocked(listIncidents).mockReset();
  vi.mocked(listIncidents).mockResolvedValue([]);
  vi.mocked(getFleetLive).mockReset();
  vi.mocked(getFleetLive).mockResolvedValue(fleetLive());
});

function fleetLive(overrides: Partial<FleetLive> = {}): FleetLive {
  return {
    range: "1h",
    step_seconds: 30,
    available: true,
    servers: [
      {
        name: "web-1",
        cpu: [[1000, 20], [1030, 42]],
        memory: [[1000, 95]],
        disk: [],
        net_in: [[1000, 2048]],
        net_out: [[1000, 1024]],
      },
    ],
    ...overrides,
  };
}

afterEach(() => {
  cleanup();
});

describe("OverviewPage", () => {
  it("shows a loading skeleton while the first request is in flight", () => {
    vi.mocked(getOverview).mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
    expect(screen.getByText("Loading the overview…")).toBeTruthy();
  });

  it("shows an error with a retry that loads the overview again", async () => {
    vi.mocked(getOverview).mockRejectedValueOnce(new Error("network down"));
    vi.mocked(getOverview).mockResolvedValueOnce(overviewFixture());
    renderPage();

    expect(await screen.findByText("The overview could not be loaded.")).toBeTruthy();
    expect(screen.getByText("network down")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("1 incident needs you.")).toBeTruthy();
    expect(getOverview).toHaveBeenCalledTimes(2);
  });

  it("leads with the status sentence and its detail as full sentences", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({ verdict: { level: "down", sentence: "The NOC itself is not working right now", detail: "The worker has never reported" } }),
    );
    renderPage();

    expect(await screen.findByText("The NOC itself is not working right now.")).toBeTruthy();
    expect(screen.getByText("The worker has never reported.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "See which part" }).getAttribute("href")).toBe("/system");
  });

  it("puts what the NOC fixed on its own before what needs a person", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    renderPage();

    const fixedFact = await screen.findByRole("link", { name: /fixed on its own in the last 24 hours/ });
    const needsFact = screen.getByRole("link", { name: /needs you/ });
    expect(fixedFact.textContent).toContain("1");
    expect(fixedFact.getAttribute("href")).toBe("/incidents?filter=resolved");
    expect(fixedFact.compareDocumentPosition(needsFact) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it("shows the incident to act on, the fixed incident, the activity and the servers", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    renderPage();

    expect(await screen.findByRole("heading", { name: "Needs you" })).toBeTruthy();
    expect(screen.getByText("Disk almost full on demo-1")).toBeTruthy();
    expect(screen.getByRole("link", { name: "demo-shop.service stopped" })).toBeTruthy();
    expect(screen.getByText(/did it on its own/)).toBeTruthy();
    expect(screen.getByText("Incident opened: DiskAlmostFull")).toBeTruthy();
    expect(screen.getByRole("link", { name: /demo-1/ })).toBeTruthy();
  });

  it("keeps the charts and the NOC health behind More details", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({ servers: [serverSummary({ id: "a", name: "web-1", open_incidents: 0, metrics: { cpu_percent: 42, memory_percent: 95, disk_percent: 50, disk_mount: "/" } })] }),
    );
    renderPage();

    expect(await screen.findByText("More details")).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Incidents, last 14 days" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Top root causes" })).toBeTruthy();
    expect(getMetrics).toHaveBeenCalledWith(14);
    expect(screen.getByText("Recent activity")).toBeTruthy();
    expect(await screen.findByText("The worker has never reported")).toBeTruthy();
  });

  it("keeps the rest of the page when the history fails", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    vi.mocked(getMetrics).mockRejectedValue(new Error("metrics down"));
    renderPage();

    expect(await screen.findByText("The history could not be loaded. It is tried again every minute.")).toBeTruthy();
    expect(screen.getByText("Disk almost full on demo-1")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Top root causes" })).toBeNull();
  });

  it("offers Mark resolved to an operator", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    renderPage();

    expect(await screen.findByRole("button", { name: "Mark resolved" })).toBeTruthy();
  });

  it("hides Mark resolved from a viewer", async () => {
    session.role = "viewer";
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    renderPage();

    expect(await screen.findByText("Disk almost full on demo-1")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Mark resolved" })).toBeNull();
  });

  it("says the numbers come from a demo run when answers are replayed", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    vi.mocked(getLlmStatus).mockResolvedValue(llmStatus("replay"));
    renderPage();

    expect(await screen.findByText(/replaying recorded answers/)).toBeTruthy();
  });

  it("hides Needs you and explains the empty lists when all is quiet", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({
        verdict: { level: "ok", sentence: "Everything is running normally", detail: "Watching 0 servers" },
        needs_attention: [],
        fixed: [],
        activity: [],
        servers: [],
      }),
    );
    renderPage();

    expect(await screen.findByText("Everything is running normally.")).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Needs you" })).toBeNull();
    expect(screen.getByText("Nothing needed fixing in the last 24 hours.")).toBeTruthy();
    expect(screen.getByText("Nothing has happened yet.")).toBeTruthy();
    expect(screen.getByText("No servers yet.")).toBeTruthy();
    expect(await screen.findByText("Nothing else is in progress right now.")).toBeTruthy();
  });

  it("names how each incident was fixed", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({
        fixed: [
          fixedItem({ incident_id: "a", kind: "approved", title: "Approved fix" }),
          fixedItem({ incident_id: "b", kind: "by_itself", title: "Went away" }),
        ],
      }),
    );
    renderPage();

    expect(await screen.findByText(/Fixed after your approval on demo-1/)).toBeTruthy();
    expect(screen.getByText(/Went away on its own on demo-1/)).toBeTruthy();
  });

  it("shows each server as a live card with CPU, memory, disk and internet", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({ servers: [serverSummary({ id: "a", name: "web-1", open_incidents: 0 })] }),
    );
    renderPage();

    const card = await screen.findByRole("article", { name: "web-1" });
    expect(await within(card).findByText("42 %")).toBeTruthy();
    expect(within(card).getByText("95 %").className).toContain("text-critical");
    expect(within(card).getByText("2.0 KB/s")).toBeTruthy();
    expect(within(card).getByText("No open incidents")).toBeTruthy();
    expect(getFleetLive).toHaveBeenCalledWith("1h");
  });

  it("asks for another time range when the dropdown changes", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    renderPage();

    fireEvent.change(await screen.findByRole("combobox", { name: "Time range" }), { target: { value: "15m" } });

    await waitFor(() => expect(getFleetLive).toHaveBeenCalledWith("15m"));
  });

  it("says when live readings cannot be read", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    vi.mocked(getFleetLive).mockResolvedValue(fleetLive({ available: false }));
    renderPage();

    expect(await screen.findByText(/Live readings are not available right now/)).toBeTruthy();
  });

  it("shows one short line instead of empty tiles for a server without readings", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture({ servers: [serverSummary({ id: "b", name: "db-1" })] }));
    renderPage();

    const card = await screen.findByRole("article", { name: "db-1" });
    expect(await within(card).findByText("No live readings from this server.")).toBeTruthy();
  });
});
