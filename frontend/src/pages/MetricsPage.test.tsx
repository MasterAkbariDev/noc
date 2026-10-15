import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { getMetrics } from "../api/client";
import type { Metrics } from "../api/types";
import { minutes, parseRange, percent } from "../features/metrics/view";
import { MetricsPage } from "./MetricsPage";

vi.mock("../api/client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("../api/client")>()),
  getMetrics: vi.fn(),
}));

const METRICS: Metrics = {
  days: 14,
  since: "2026-10-02T00:00:00Z",
  totals: {
    incidents: 12,
    resolved: 6,
    escalated: 2,
    open: 4,
    auto_resolved_share: 0.75,
    median_minutes_to_resolve: 4.5,
    median_minutes_to_diagnose: 0.5,
    llm_calls: 1540,
    llm_failures: 3,
    tokens: 2_400_000,
    tool_calls: 88,
    actions_run: 5,
    reviewed: 4,
    confirmed: 3,
  },
  per_day: [
    { day: "2026-10-14", opened: 4, resolved: 3, escalated: 1, llm_calls: 500, tokens: 900_000, tool_calls: 30 },
    { day: "2026-10-15", opened: 8, resolved: 3, escalated: 1, llm_calls: 1040, tokens: 1_500_000, tool_calls: 58 },
  ],
  root_causes: [
    { label: "service_crashed", count: 7 },
    { label: "other", count: 5 },
  ],
  outcomes: [{ label: "RESOLVED", count: 6 }],
  actions: [{ label: "succeeded", count: 5 }],
  variants: [
    { variant: "multi", incidents: 8, resolved: 5, escalated: 1, llm_calls: 1200 },
    { variant: "runbook", incidents: 4, resolved: 1, escalated: 1, llm_calls: 0 },
  ],
};

function renderPage(path = "/stats") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <MetricsPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(getMetrics).mockReset();
  vi.mocked(getMetrics).mockResolvedValue(METRICS);
});

afterEach(() => {
  cleanup();
});

describe("MetricsPage", () => {
  it("shows the key figures in words people use", async () => {
    renderPage();
    const figures = await screen.findByRole("region", { name: "Key figures" });
    expect(within(figures).getByText("75%")).toBeTruthy();
    expect(within(figures).getByText("6 of 8 finished incidents")).toBeTruthy();
    expect(within(figures).getByText("4.5 min")).toBeTruthy();
    expect(within(figures).getByText("30 s")).toBeTruthy();
    expect(within(figures).getByText("1.5K")).toBeTruthy();
    expect(within(figures).getByText("2.4M tokens, 3 failed")).toBeTruthy();
    expect(within(figures).getByText("3 of 4")).toBeTruthy();
  });

  it("draws the charts with plain labels and a variants table", async () => {
    renderPage();
    await screen.findByRole("region", { name: "Key figures" });
    expect(screen.getByRole("img", { name: "Incidents opened per day" })).toBeTruthy();
    expect(screen.getByRole("img", { name: "Tokens per day" })).toBeTruthy();
    const causes = screen.getByRole("list", { name: "Root causes" });
    expect(within(causes).getByText("Service crashed")).toBeTruthy();
    expect(within(causes).getByText("Other")).toBeTruthy();
    const variants = screen.getByRole("table", { name: "Incidents by investigation variant" });
    expect(within(variants).getByText("Runbook (no model)")).toBeTruthy();
    expect(within(variants).getByText("150.0")).toBeTruthy();
    expect(within(variants).getByText("0.0")).toBeTruthy();
  });

  it("reads the range from the address and asks the server for it", async () => {
    renderPage("/stats?days=30");
    await screen.findByRole("region", { name: "Key figures" });
    expect(getMetrics).toHaveBeenCalledWith(30);
    fireEvent.change(screen.getByLabelText("Time range"), { target: { value: "7" } });
    await waitFor(() => expect(getMetrics).toHaveBeenCalledWith(7));
  });

  it("offers a retry when the metrics cannot be loaded", async () => {
    vi.mocked(getMetrics).mockRejectedValue(new Error("down"));
    renderPage();
    expect(await screen.findByText("Could not load the metrics")).toBeTruthy();
  });
});

describe("metrics view helpers", () => {
  it("falls back to 14 days for odd ranges", () => {
    expect(parseRange("30")).toBe(30);
    expect(parseRange("31")).toBe(14);
    expect(parseRange(null)).toBe(14);
  });

  it("formats durations and shares", () => {
    expect(minutes(null)).toBe("–");
    expect(minutes(0.25)).toBe("15 s");
    expect(minutes(45)).toBe("45 min");
    expect(minutes(180)).toBe("3.0 h");
    expect(percent(null)).toBe("–");
    expect(percent(0.333)).toBe("33%");
  });
});
