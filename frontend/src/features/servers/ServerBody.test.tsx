import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ApiError, getServer, getServerLive } from "../../api/client";
import type { ServerDetail, ServerLive } from "../../api/types";
import { TooltipProvider } from "../../ui/Tooltip";
import { ServerBody } from "./ServerBody";
import { useServerQuery } from "./queries";
import { detailFixture, HOSTILE_TEXT, incidentFixture, SERVER_ID } from "./fixtures";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getServer: vi.fn(),
  getServerLive: vi.fn(),
}));

function Harness() {
  const query = useServerQuery(SERVER_ID);
  return <ServerBody query={query} />;
}

function renderBody() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter>
          <Harness />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function serveDetail(overrides: Partial<ServerDetail> = {}) {
  vi.mocked(getServer).mockResolvedValue(detailFixture(overrides));
}

function liveFixture(overrides: Partial<ServerLive> = {}): ServerLive {
  return {
    range: "1h",
    step_seconds: 30,
    available: true,
    cpu: [[1000, 12], [1030, 16]],
    memory: [[1000, 60]],
    disk: [],
    load: [[1000, 0.5], [1030, 3]],
    net_in: [],
    net_out: [],
    net_errors: [],
    disk_read: [],
    disk_write: [],
    uptime_seconds: 90_000,
    cpu_count: 2,
    services: [{ resource_id: "svc-a", name: "nginx", up: true, memory_bytes: [[1000, 52_428_800]], memory_limit_bytes: 104_857_600 }],
    ...overrides,
  };
}

beforeEach(() => {
  vi.mocked(getServer).mockReset();
  vi.mocked(getServerLive).mockReset();
  vi.mocked(getServerLive).mockResolvedValue(liveFixture());
});

afterEach(() => {
  cleanup();
});

describe("ServerBody", () => {
  it("shows the services with their state as text", async () => {
    serveDetail({
      services: [
        { resource_id: "svc-a", name: "nginx", up: true },
        { resource_id: "svc-b", name: "postgres", up: false },
        { resource_id: "svc-c", name: "redis", up: null },
      ],
    });
    renderBody();

    expect(await screen.findByText("nginx")).toBeTruthy();
    expect(screen.getByText("Up")).toBeTruthy();
    expect(screen.getByText("Down")).toBeTruthy();
    expect(screen.getByText("Unknown")).toBeTruthy();
  });

  it("says Metrics unavailable instead of showing zeros when Prometheus gave nothing", async () => {
    serveDetail({ metrics: null });
    renderBody();

    expect(await screen.findByText("Metrics unavailable")).toBeTruthy();
    expect(screen.queryByRole("meter")).toBeNull();
  });

  it("shows never for a server without an inventory or scrape time", async () => {
    serveDetail({ last_inventory_at: null, last_scrape_at: null });
    renderBody();

    await screen.findByText("Right now");
    expect(screen.getAllByText("never").length).toBe(2);
  });

  it("lists the recent incidents as links to the incident page", async () => {
    serveDetail({ recent_incidents: [incidentFixture({ id: "inc-9", title: "Disk filling" })] });
    renderBody();

    const link = await screen.findByRole("link", { name: "Disk filling" });
    expect(link.getAttribute("href")).toBe("/incidents/inc-9");
  });

  it("says so when the server has no incidents", async () => {
    serveDetail({ recent_incidents: [] });
    renderBody();

    expect(await screen.findByText("No incidents have been recorded for this server.")).toBeTruthy();
  });

  it("shows a hostile service and resource name as text and creates no image element", async () => {
    serveDetail({
      services: [{ resource_id: "svc-a", name: HOSTILE_TEXT, up: true }],
      resources: [{ resource_id: "svc-a", kind: "systemd_unit", name: HOSTILE_TEXT }],
    });
    const { container } = renderBody();

    expect((await screen.findAllByText(HOSTILE_TEXT)).length).toBe(2);
    expect(container.querySelector("img")).toBeNull();
  });

  it("shows a not-found state for an unknown server", async () => {
    vi.mocked(getServer).mockRejectedValue(new ApiError(404, "server not found"));
    renderBody();

    expect(await screen.findByText("Server not found")).toBeTruthy();
  });

  it("shows an error with a retry that asks again", async () => {
    vi.mocked(getServer).mockRejectedValueOnce(new ApiError(500, "database is busy"));
    serveDetail();
    renderBody();

    expect(await screen.findByText("database is busy")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByText("Right now")).toBeTruthy();
    expect(getServer).toHaveBeenCalledTimes(2);
  });

  it("shows live charts with uptime and the load in plain words", async () => {
    serveDetail();
    renderBody();

    expect(await screen.findByRole("heading", { name: "CPU" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Internet traffic" })).toBeTruthy();
    expect(screen.getByText("1 day 1 h")).toBeTruthy();
    expect(screen.getByText("3.00 on 2 cores, overloaded")).toBeTruthy();
    expect(screen.getAllByText(/No network readings/).length).toBeGreaterThan(0);
    expect(getServerLive).toHaveBeenCalledWith(expect.any(String), "1h");
  });

  it("adds each service's memory use to the service list", async () => {
    serveDetail({ services: [{ resource_id: "svc-a", name: "nginx", up: true }] });
    renderBody();

    expect(await screen.findByText("uses 50 MB of its 100 MB memory limit")).toBeTruthy();
  });

  it("says when live readings are not available", async () => {
    serveDetail();
    vi.mocked(getServerLive).mockResolvedValue(liveFixture({ available: false }));
    renderBody();

    expect(await screen.findByText(/Live readings are not available right now/)).toBeTruthy();
  });
});
