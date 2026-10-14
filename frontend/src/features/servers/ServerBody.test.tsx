import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ApiError, getServer } from "../../api/client";
import type { ServerDetail } from "../../api/types";
import { TooltipProvider } from "../../ui/Tooltip";
import { ServerBody } from "./ServerBody";
import { useServerQuery } from "./queries";
import { detailFixture, HOSTILE_TEXT, incidentFixture, SERVER_ID } from "./fixtures";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getServer: vi.fn(),
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

beforeEach(() => {
  vi.mocked(getServer).mockReset();
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

    await screen.findByText("Metrics");
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

    expect(await screen.findByText("Metrics")).toBeTruthy();
    expect(getServer).toHaveBeenCalledTimes(2);
  });
});
