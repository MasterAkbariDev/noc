import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { ApiError, getServers } from "../../api/client";
import { useSession } from "../../auth/session";
import { sessionFor } from "../settings/fixtures";
import { TooltipProvider } from "../../ui/Tooltip";
import { ServersList } from "./ServersList";
import { HOSTILE_TEXT, summaryFixture } from "./fixtures";

vi.mock("../../auth/session", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../auth/session")>()),
  useSession: vi.fn(),
}));

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  getServers: vi.fn(),
}));

function renderList() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter>
          <ServersList />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(useSession).mockReturnValue(sessionFor({ username: "viewer", role: "viewer", via: "session" }));
  vi.mocked(getServers).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("ServersList", () => {
  it("shows a loading skeleton while the first request is in flight", () => {
    vi.mocked(getServers).mockReturnValue(new Promise(() => undefined));
    renderList();

    expect(screen.getByRole("status")).toBeTruthy();
  });

  it("shows an error with a retry that asks again", async () => {
    vi.mocked(getServers).mockRejectedValueOnce(new ApiError(500, "database is busy"));
    vi.mocked(getServers).mockResolvedValueOnce([summaryFixture()]);
    renderList();

    expect(await screen.findByText("database is busy")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("link", { name: "web-1" })).toBeTruthy();
    expect(getServers).toHaveBeenCalledTimes(2);
  });

  it("shows an empty state when no server is registered", async () => {
    vi.mocked(getServers).mockResolvedValue([]);
    renderList();

    expect(await screen.findByText("No servers yet")).toBeTruthy();
  });

  it("shows one card per server, in the order the API returns them", async () => {
    vi.mocked(getServers).mockResolvedValue([
      summaryFixture({ id: "a", name: "alpha" }),
      summaryFixture({ id: "b", name: "beta", halted: true }),
    ]);
    renderList();

    const cards = await screen.findByRole("list", { name: "Server cards" });
    expect(within(cards).getAllByRole("link").map((link) => link.textContent)).toEqual(["alpha", "beta"]);
    expect(screen.getByText("Halted")).toBeTruthy();
  });

  it("sums the fleet above the cards from what the API reported", async () => {
    vi.mocked(getServers).mockResolvedValue([
      summaryFixture({ id: "a", name: "alpha", status: "up", open_incidents: 2 }),
      summaryFixture({ id: "b", name: "beta", status: "down", open_incidents: 1, halted: true }),
    ]);
    renderList();

    const summary = await screen.findByRole("region", { name: "Fleet summary" });
    expect(within(summary).getByText("1 reachable now")).toBeTruthy();
    expect(within(summary).getByRole("link", { name: /Open incidents/ }).textContent).toContain("3");
    expect(within(summary).getByText("Servers where the NOC only watches").parentElement?.textContent).toBe("Automation halted1Servers where the NOC only watches");
  });

  it("shows a hostile server name as text and creates no image element", async () => {
    vi.mocked(getServers).mockResolvedValue([summaryFixture({ name: HOSTILE_TEXT })]);
    const { container } = renderList();

    expect(await screen.findByRole("link", { name: HOSTILE_TEXT })).toBeTruthy();
    expect(container.querySelector("img")).toBeNull();
  });
});
