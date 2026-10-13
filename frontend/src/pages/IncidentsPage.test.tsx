import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes } from "react-router";
import type { IncidentSummary } from "../api/types";
import { TOKEN_STORAGE_KEY, TokenProvider } from "../auth/token";
import { IncidentsPage } from "./IncidentsPage";

const fetchMock = vi.fn<typeof fetch>();

const incidents: IncidentSummary[] = [
  {
    id: "11111111-1111-1111-1111-111111111111",
    title: "Critical one",
    status: "NEW",
    severity: "critical",
    target: "web-1",
    opened_at: "2026-10-12T10:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
  },
  {
    id: "22222222-2222-2222-2222-222222222222",
    title: "Warning one",
    status: "NEW",
    severity: "warning",
    target: "db-1",
    opened_at: "2026-10-12T11:00:00Z",
    root_cause_code: null,
    confidence: null,
    escalation_reason: null,
  },
];

function renderList(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TokenProvider>
        <MemoryRouter initialEntries={[path]}>
          <Routes>
            <Route path="/incidents" element={<IncidentsPage />} />
          </Routes>
        </MemoryRouter>
      </TokenProvider>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  sessionStorage.setItem(TOKEN_STORAGE_KEY, "secret-token");
  fetchMock.mockResolvedValue(
    new Response(JSON.stringify(incidents), { status: 200, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  sessionStorage.clear();
});

describe("IncidentsPage", () => {
  it("shows only the incidents of the severity named in the URL", async () => {
    renderList("/incidents?severity=critical");

    expect(await screen.findByRole("link", { name: "Critical one" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Warning one" })).toBeNull();
    expect((screen.getByLabelText(/Severity/) as HTMLSelectElement).value).toBe("critical");
  });

  it("offers every severity in the fetched list when no severity is chosen", async () => {
    renderList("/incidents");

    expect(await screen.findByRole("link", { name: "Warning one" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Critical one" })).toBeTruthy();
  });
});
