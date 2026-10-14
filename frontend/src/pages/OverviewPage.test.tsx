import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { getOverview } from "../api/client";
import type { Role } from "../api/types";
import { overviewFixture } from "../features/overview/testData";
import { OverviewPage } from "./OverviewPage";

const session = vi.hoisted(() => ({ role: "operator" as Role }));

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getOverview: vi.fn(),
}));

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
