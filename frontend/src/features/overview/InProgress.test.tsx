import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { listIncidents } from "../../api/client";
import type { IncidentSummary } from "../../api/types";
import { HOSTILE_SCRIPT } from "./testData";
import { InProgress } from "./InProgress";

vi.mock("../../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../../api/client")>()),
  listIncidents: vi.fn(),
}));

function incident(overrides: Partial<IncidentSummary> = {}): IncidentSummary {
  return {
    id: "11111111-1111-1111-1111-111111111111",
    title: "Disk almost full on demo-1",
    status: "INVESTIGATING",
    severity: "critical",
    target: "demo-1",
    opened_at: "2026-10-14T10:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
    ...overrides,
  };
}

function renderInProgress() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <InProgress />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(listIncidents).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("InProgress", () => {
  it("lists only the incidents that are moving, not the ones waiting for a person", async () => {
    vi.mocked(listIncidents).mockResolvedValue([
      incident({ id: "a", title: "Disk on demo-1", status: "INVESTIGATING" }),
      incident({ id: "b", title: "Fixing demo-2", status: "REMEDIATING" }),
      incident({ id: "c", title: "Waiting on demo-3", status: "AWAITING_APPROVAL" }),
      incident({ id: "d", title: "Escalated demo-4", status: "ESCALATED" }),
      incident({ id: "e", title: "Old blip demo-5", status: "RESOLVED" }),
    ]);
    renderInProgress();

    expect(await screen.findByText("Disk on demo-1")).toBeTruthy();
    expect(screen.getByText("Fixing demo-2")).toBeTruthy();
    expect(screen.queryByText("Waiting on demo-3")).toBeNull();
    expect(screen.queryByText("Escalated demo-4")).toBeNull();
    expect(screen.queryByText("Old blip demo-5")).toBeNull();
  });

  it("shows the plain status label and how long ago the incident started", async () => {
    vi.mocked(listIncidents).mockResolvedValue([incident({ status: "REMEDIATING" })]);
    renderInProgress();

    expect(await screen.findByText(/Taking action, started/)).toBeTruthy();
  });

  it("links each incident to its page", async () => {
    vi.mocked(listIncidents).mockResolvedValue([incident()]);
    renderInProgress();

    const link = await screen.findByRole("link", { name: "Disk almost full on demo-1" });
    expect(link.getAttribute("href")).toBe("/incidents/11111111-1111-1111-1111-111111111111");
  });

  it("shows the empty state when nothing is moving", async () => {
    vi.mocked(listIncidents).mockResolvedValue([incident({ status: "RESOLVED" })]);
    renderInProgress();

    expect(await screen.findByText("Nothing else is in progress right now.")).toBeTruthy();
  });

  it("shows an error with a retry that asks again", async () => {
    vi.mocked(listIncidents)
      .mockRejectedValueOnce(new Error("network down"))
      .mockResolvedValueOnce([incident()]);
    renderInProgress();

    expect(await screen.findByText("Incidents in progress could not be loaded.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));

    await waitFor(() => expect(screen.getByText("Disk almost full on demo-1")).toBeTruthy());
    expect(listIncidents).toHaveBeenCalledTimes(2);
  });

  it("shows a hostile incident title as text and creates no element for it", async () => {
    vi.mocked(listIncidents).mockResolvedValue([incident({ title: HOSTILE_SCRIPT })]);
    const { container } = renderInProgress();

    expect(await screen.findByText(HOSTILE_SCRIPT)).toBeTruthy();
    expect(container.querySelector("script")).toBeNull();
  });
});
