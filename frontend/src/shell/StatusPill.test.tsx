import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import { getOverview } from "../api/client";
import type { Overview, VerdictLevel } from "../api/types";
import { TOKEN_STORAGE_KEY, TokenProvider } from "../auth/token";
import { StatusPill } from "./StatusPill";

vi.mock("../api/client", () => ({ getOverview: vi.fn() }));

const DOT_CLASSES: Record<VerdictLevel, string> = {
  ok: "bg-ok",
  attention: "bg-warning",
  degraded: "bg-warning",
  down: "bg-critical",
};

function overviewFixture(level: VerdictLevel, sentence: string): Overview {
  return {
    verdict: { level, sentence },
    kpis: {
      open_incidents: 0,
      needs_you: 0,
      servers_up: 0,
      servers_total: 0,
      llm_keys_ok: 0,
      llm_keys_total: 0,
    },
    needs_attention: [],
    activity: [],
    servers: [],
  };
}

function renderPill() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TokenProvider>
        <MemoryRouter>
          <StatusPill />
        </MemoryRouter>
      </TokenProvider>
    </QueryClientProvider>,
  );
}

function dotClass(link: HTMLElement): string {
  return link.querySelector("span[aria-hidden='true']")?.className ?? "";
}

beforeEach(() => {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, "t");
  vi.mocked(getOverview).mockReset();
});

afterEach(() => {
  cleanup();
  sessionStorage.clear();
});

describe("StatusPill", () => {
  it.each<[VerdictLevel, string]>([
    ["ok", "All systems operational"],
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

  it("asks for the token and sends no request without one", () => {
    sessionStorage.clear();
    renderPill();

    expect(screen.getByText("Enter the API token to see status")).toBeTruthy();
    expect(getOverview).not.toHaveBeenCalled();
  });
});
