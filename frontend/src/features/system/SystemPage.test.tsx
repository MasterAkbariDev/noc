import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router";
import type { LlmStatus, StuckIncident, SystemHealth } from "../../api/types";
import { SystemPage } from "../../pages/SystemPage";
import { TooltipProvider } from "../../ui";

const fetchMock = vi.fn<typeof fetch>();

const HOSTILE_ERROR = '<img src=x onerror="alert(1)"><script>alert(2)</script>job crashed';

const health: SystemHealth = {
  verdict: "degraded",
  checked_at: "2026-10-12T10:00:00Z",
  components: [
    { key: "worker", label: "Worker", status: "ok", summary: "Worker is beating", details: {}, since: null },
    {
      key: "prometheus",
      label: "Prometheus",
      status: "degraded",
      summary: "1 of 3 scrape targets are down",
      details: { up: "2/3" },
      since: "2026-10-12T09:00:00Z",
    },
  ],
  stuck_incidents: [],
};

const llm: LlmStatus = {
  mode: "replay",
  keys: [
    {
      label: "gemini#1a2b3c4d",
      provider: "gemini",
      state: "ok",
      cooling_until: null,
      last_error: null,
      last_error_at: null,
      last_success_at: null,
      models: [{ tier: "strong", model: "gemini-2.5-pro", used_today: 3, daily_limit: 50 }],
    },
  ],
};

const stuck: StuckIncident = {
  id: "22222222-2222-2222-2222-222222222222",
  title: "Disk almost full on db-1",
  target: "db-1",
  status: "REMEDIATING",
  since: "2026-10-12T08:00:00Z",
  job_status: "failed",
  job_attempts: 2,
  job_last_error: HOSTILE_ERROR,
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

function serve(healthBody: unknown, llmBody: unknown = llm) {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/system/health") {
      return jsonResponse(healthBody);
    }
    if (url === "/api/system/llm") {
      return jsonResponse(llmBody);
    }
    throw new Error(`unexpected request ${url}`);
  });
}

function requestCount(path: string): number {
  return fetchMock.mock.calls.filter(([input]) => String(input) === path).length;
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <MemoryRouter>
          <SystemPage />
        </MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("SystemPage", () => {
  it("sets the document title and shows the verdict in the header", async () => {
    serve(health);
    renderPage();

    expect(await screen.findByText(/Some parts are degraded/)).toBeTruthy();
    await waitFor(() => expect(document.title).toBe("System · NOC"));
  });

  it("shows a card for each component and the LLM mode, keys and usage", async () => {
    serve(health);
    renderPage();

    expect(await screen.findByRole("region", { name: "Prometheus" })).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Worker" })).getByText("Healthy")).toBeTruthy();
    expect(within(screen.getByRole("region", { name: "Prometheus" })).getByText("Degraded")).toBeTruthy();
    expect(screen.getByText("gemini#1a2b3c4d")).toBeTruthy();
    expect(screen.getByText("3 of 50 used today")).toBeTruthy();
  });

  it("explains replay mode when the LLM runs from a recording", async () => {
    serve(health);
    renderPage();

    expect(await screen.findByRole("note")).toBeTruthy();
  });

  it("says None when no incident is stuck", async () => {
    serve(health);
    renderPage();

    expect(await screen.findByText(/^None\./)).toBeTruthy();
  });

  it("lists stuck incidents and shows a hostile job error as text", async () => {
    serve({ ...health, verdict: "down", stuck_incidents: [stuck] });
    const { container } = renderPage();

    expect(await screen.findByRole("link", { name: "Disk almost full on db-1" })).toBeTruthy();
    expect(screen.getByText(HOSTILE_ERROR).tagName).toBe("CODE");
    expect(container.querySelector("img")).toBeNull();
    expect(container.querySelector("script")).toBeNull();
  });

  it("shows an error with a retry button when system health fails, and retries", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/system/health") {
        return requestCount(url) === 1 ? jsonResponse({ detail: "database offline" }, 500) : jsonResponse(health);
      }
      return jsonResponse(llm);
    });
    renderPage();

    const [alert] = await screen.findAllByRole("alert");
    expect(within(alert!).getByText("database offline")).toBeTruthy();

    fireEvent.click(within(alert!).getByRole("button", { name: "Try again" }));

    expect(await screen.findByRole("region", { name: "Worker" })).toBeTruthy();
    expect(requestCount("/api/system/health")).toBe(2);
  });

  it("keeps the LLM section working when only the health request fails", async () => {
    fetchMock.mockImplementation(async (input) => {
      const url = String(input);
      if (url === "/api/system/health") {
        return jsonResponse({ detail: "database offline" }, 500);
      }
      return jsonResponse(llm);
    });
    renderPage();

    expect(await screen.findByText("gemini#1a2b3c4d")).toBeTruthy();
    expect(screen.getByText("Status unavailable")).toBeTruthy();
  });
});
