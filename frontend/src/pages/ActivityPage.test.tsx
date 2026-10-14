import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { getActivity, verifyActivity, type ActivityQuery } from "../api/client";
import type { ActivityPage as ActivityPageData } from "../api/types";
import { entryFixture } from "../features/activity/fixtures";
import { TooltipProvider } from "../ui/Tooltip";
import { ActivityPage } from "./ActivityPage";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getActivity: vi.fn(),
  verifyActivity: vi.fn(),
}));

const NEWEST = entryFixture({ id: 30, summary: "alice closed incident 3f2a" });
const MIDDLE = entryFixture({ id: 20, actor: "bob", action: "login", action_label: "Signed in", summary: "Bob signed in" });
const OLDEST = entryFixture({ id: 10, actor: "carol", summary: "carol changed a role" });

function serveFeed(query: ActivityQuery): Promise<ActivityPageData> {
  if (query.before_id === undefined) {
    return Promise.resolve({ items: [NEWEST, MIDDLE], next_before_id: 20 });
  }
  return Promise.resolve({ items: [OLDEST], next_before_id: null });
}

function renderPage(path = "/activity") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter initialEntries={[path]}>
          <ActivityPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getActivity).mockReset();
  vi.mocked(verifyActivity).mockReset();
  vi.mocked(verifyActivity).mockResolvedValue({ ok: true, broken_at: null });
  vi.mocked(getActivity).mockImplementation((query = {}) => serveFeed(query));
});

afterEach(() => {
  cleanup();
});

describe("ActivityPage", () => {
  it("shows the first page and appends the next one on Load more", async () => {
    renderPage();

    expect(await screen.findByText("alice closed incident 3f2a")).toBeTruthy();
    expect(screen.getByText("Bob signed in")).toBeTruthy();
    expect(screen.queryByText("carol changed a role")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Load more" }));

    expect(await screen.findByText("carol changed a role")).toBeTruthy();
    expect(screen.getAllByRole("row")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: "Load more" })).toBeNull();
    expect(getActivity).toHaveBeenLastCalledWith(expect.objectContaining({ before_id: 20 }));
  });

  it("shows that the audit log is intact when the chain verifies", async () => {
    renderPage();

    expect(await screen.findByText("Audit log intact")).toBeTruthy();
  });

  it("warns with the broken entry number when the chain does not verify", async () => {
    vi.mocked(verifyActivity).mockResolvedValue({ ok: false, broken_at: 20 });
    renderPage();

    expect(await screen.findByText("Audit log broken at entry 20")).toBeTruthy();
  });

  it("puts the chosen action in the URL and asks the API for only that action", async () => {
    renderPage();
    await screen.findByText("Bob signed in");

    fireEvent.change(screen.getByLabelText("Action"), { target: { value: "login" } });

    await waitFor(() => {
      expect(getActivity).toHaveBeenLastCalledWith(
        expect.objectContaining({ action: "login", before_id: undefined }),
      );
    });
  });

  it("reads the filters from the URL on first load", async () => {
    renderPage("/activity?actor=bob");

    await screen.findByText("Bob signed in");

    expect(getActivity).toHaveBeenCalledWith(expect.objectContaining({ actor: "bob" }));
    expect((screen.getByLabelText("Who") as HTMLInputElement).value).toBe("bob");
  });
});
