import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { getOverview } from "../api/client";
import type { Overview } from "../api/types";
import type { OverviewLevel } from "../lib/tones";
import { StatusPill } from "./StatusPill";

vi.mock("../api/client", () => ({ getOverview: vi.fn() }));

const DOT_CLASSES: Record<OverviewLevel, string> = {
  ok: "bg-ok",
  working: "bg-info",
  attention: "bg-warning",
  degraded: "bg-warning",
  down: "bg-critical",
};

function overviewFixture(level: OverviewLevel, sentence: string): Overview {
  return {
    verdict: { level, sentence },
    kpis: {
      open_incidents: 0,
      needs_you: 0,
      servers_up: 0,
      servers_total: 0,
      llm_keys_ok: 0,
      llm_keys_total: 0,
      fixed_today: 2,
      fixed_automatically_today: 1,
    },
    needs_attention: [],
    fixed: [],
    activity: [],
    servers: [],
  };
}

function renderPill() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <StatusPill />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function dotClass(link: HTMLElement): string {
  return link.querySelector("span[aria-hidden='true']")?.className ?? "";
}

beforeEach(() => {
  vi.mocked(getOverview).mockReset();
});

afterEach(() => {
  cleanup();
});

describe("StatusPill", () => {
  it.each<[OverviewLevel, string]>([
    ["ok", "2 servers · 0 open incidents · LLM OK"],
    ["working", "Working on 1 incident · 2 servers up · LLM OK"],
    ["attention", "1 incident needs you"],
    ["degraded", "The LLM provider is degraded"],
    ["down", "The NOC is not working"],
  ])("shows the %s verdict as a link to the overview", async (level, sentence) => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture(level, sentence));
    renderPill();

    const link = await screen.findByRole("link", { name: sentence });

    expect(link.getAttribute("href")).toBe("/");
    expect(dotClass(link)).toContain(DOT_CLASSES[level]);
  });

  it("shows Checking while the first request is in flight", () => {
    vi.mocked(getOverview).mockReturnValue(new Promise(() => undefined));
    renderPill();

    expect(screen.getByText("Checking…")).toBeTruthy();
  });

  it("shows Status unavailable when the request fails", async () => {
    vi.mocked(getOverview).mockRejectedValue(new Error("network down"));
    renderPill();

    await waitFor(() => expect(screen.getByText("Status unavailable")).toBeTruthy());
  });

  it("loads the overview once without any credential argument", async () => {
    vi.mocked(getOverview).mockResolvedValue(overviewFixture("ok", "All systems operational"));
    renderPill();

    await screen.findByRole("link", { name: "All systems operational" });

    expect(getOverview).toHaveBeenCalledTimes(1);
    expect(vi.mocked(getOverview).mock.calls[0]).toEqual([]);
  });
});
