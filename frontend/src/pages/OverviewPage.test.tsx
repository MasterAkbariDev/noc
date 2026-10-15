import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { getLlmStatus, getMetrics, getOverview, getSystemHealth } from "../api/client";
import type { LlmStatus, Role } from "../api/types";
import { metricsFixture, overviewFixture, serverSummary, systemHealthFixture } from "../features/overview/testData";
import { OverviewPage } from "./OverviewPage";

const session = vi.hoisted(() => ({ role: "operator" as Role }));

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getOverview: vi.fn(),
  getLlmStatus: vi.fn(),
  getMetrics: vi.fn(),
  getSystemHealth: vi.fn(),
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
});

afterEach(() => {
  cleanup();
});

describe("OverviewPage", () => {
  it("shows a loading skeleton while the first request is in flight", () => {
    vi.mocked(getOverview).mockReturnValue(new Promise(() => undefined));
    renderPage();

    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
    expect(screen.getByText("Loading…")).toBeTruthy();
  });

  it("shows an error with a retry that loads the overview again", async () => {
    vi.mocked(getOverview).mockRejectedValueOnce(new Error("network down"));
    vi.mocked(getOverview).mockResolvedValueOnce(overviewFixture());
    renderPage();

    expect(await screen.findByText("The overview could not be loaded.")).toBeTruthy();
    expect(screen.getByText("network down")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("1 incident needs you")).toBeTruthy();
    expect(getOverview).toHaveBeenCalledTimes(2);
  });

  it("shows the verdict, the counts, the incident to act on and the servers", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    renderPage();

    expect(await screen.findByText("1 incident needs you")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Needs you/ })).toBeTruthy();
    expect(screen.getByText("Disk almost full on demo-1")).toBeTruthy();
    expect(screen.getByText("Incident opened: DiskAlmostFull")).toBeTruthy();
    expect(screen.getByRole("link", { name: "demo-1" })).toBeTruthy();
  });

  it("draws the server status, the incident trend, the server resources and the NOC health", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({
        servers: [
          serverSummary({ id: "a", name: "web-1", metrics: { cpu_percent: 42, memory_percent: 95, disk_percent: 50, disk_mount: "/" } }),
          serverSummary({ id: "b", name: "db-1", status: "down" }),
        ],
      }),
    );
    renderPage();

    expect(await screen.findByRole("img", { name: "Server status: Up 1, Down 1, Unknown 0" })).toBeTruthy();
    expect(await screen.findByRole("heading", { name: "Incidents, last 14 days" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Top root causes" })).toBeTruthy();
    expect(getMetrics).toHaveBeenCalledWith(14);

    const resources = screen.getByRole("table", { name: "Server resources" });
    expect(within(resources).getByRole("meter", { name: "Memory on web-1" }).getAttribute("aria-valuetext")).toBe("95%");
    expect(within(resources).getAllByText("No data").length).toBeGreaterThan(0);

    expect(await screen.findByText("The worker has never reported")).toBeTruthy();
  });

  it("keeps the rest of the dashboard when the incident history fails", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture());
    vi.mocked(getMetrics).mockRejectedValue(new Error("metrics down"));
    renderPage();

    expect(await screen.findByText("The incident history could not be loaded.")).toBeTruthy();
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

  it("shows Replay mode on the LLM tile instead of 0/0 when answers are replayed", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({
        kpis: { ...overviewFixture().kpis, llm_keys_ok: 0, llm_keys_total: 0 },
      }),
    );
    vi.mocked(getLlmStatus).mockResolvedValue(llmStatus("replay"));
    renderPage();

    expect(await screen.findByText("Replay mode")).toBeTruthy();
    expect(screen.getByText("recorded answers")).toBeTruthy();
    expect(screen.queryByText("0/0")).toBeNull();
  });

  it("shows the empty texts when nothing needs attention and nothing has happened", async () => {
    vi.mocked(getOverview).mockResolvedValue(
      overviewFixture({
        verdict: { level: "ok", sentence: "All systems operational" },
        needs_attention: [],
        activity: [],
        servers: [],
      }),
    );
    renderPage();

    expect(await screen.findByText("Nothing needs you right now.")).toBeTruthy();
    expect(screen.getByText("No activity yet.")).toBeTruthy();
    expect(screen.getByText("No servers yet.")).toBeTruthy();
  });
});
