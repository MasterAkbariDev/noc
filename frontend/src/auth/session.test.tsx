import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { listIncidents } from "../api/client";
import { SessionProvider, useSessionState } from "./session";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function SessionProbe() {
  const session = useSessionState();
  return (
    <div>
      <p>{session.status === "authenticated" ? `Signed in as ${session.me.username}` : session.status}</p>
      <button type="button" onClick={() => session.logout()}>
        Sign out
      </button>
      <button type="button" onClick={() => void listIncidents().catch(() => undefined)}>
        Load incidents
      </button>
    </div>
  );
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function renderSession(path: string, queryClient: QueryClient) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <SessionProvider>
          <Routes>
            <Route path="/incidents" element={<SessionProbe />} />
            <Route path="/login" element={<p>Login route</p>} />
          </Routes>
          <LocationProbe />
        </SessionProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function newQueryClient(): QueryClient {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("SessionProvider", () => {
  it("clears cached data and goes to the login page on sign out", async () => {
    fetchMock.mockImplementation(async (input) => {
      if (String(input) === "/api/auth/me") {
        return jsonResponse({ username: "alice", role: "operator", via: "session" });
      }
      return new Response(null, { status: 204 });
    });
    const queryClient = newQueryClient();
    queryClient.setQueryData(["incidents"], [{ id: "secret-incident" }]);
    renderSession("/incidents", queryClient);

    expect(await screen.findByText("Signed in as alice")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Sign out" }));

    expect(await screen.findByText("Login route")).toBeTruthy();
    expect(queryClient.getQueryData(["incidents"])).toBeUndefined();
    const logoutCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/auth/logout");
    expect(logoutCall?.[1]?.method).toBe("POST");
  });

  it("ends the session on a 401 from a data request and returns to login with the path to come back to", async () => {
    fetchMock.mockImplementation(async (input) => {
      if (String(input) === "/api/auth/me") {
        return jsonResponse({ username: "alice", role: "viewer", via: "session" });
      }
      return jsonResponse({ detail: "unauthorized" }, 401);
    });
    const queryClient = newQueryClient();
    queryClient.setQueryData(["incidents"], [{ id: "secret-incident" }]);
    renderSession("/incidents", queryClient);

    await screen.findByText("Signed in as alice");
    fireEvent.click(screen.getByRole("button", { name: "Load incidents" }));

    expect(await screen.findByText("Login route")).toBeTruthy();
    expect(screen.getByTestId("location").textContent).toBe("/login?expired=1&next=%2Fincidents");
    expect(queryClient.getQueryData(["incidents"])).toBeUndefined();
  });

  it("reports an anonymous visitor as anonymous without a signed-in user", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "unauthorized" }, 401));
    renderSession("/incidents", newQueryClient());

    await waitFor(() => expect(screen.getByText("anonymous")).toBeTruthy());
    expect(screen.queryByText(/Signed in as/)).toBeNull();
  });

  it("reports an unreachable NOC, not a signed-out visitor, when the server fails", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "upstream down" }, 502));
    renderSession("/incidents", newQueryClient());

    await waitFor(() => expect(screen.getByText("unreachable")).toBeTruthy());
  });

  it("reports an unreachable NOC when the request cannot be sent", async () => {
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
    renderSession("/incidents", newQueryClient());

    await waitFor(() => expect(screen.getByText("unreachable")).toBeTruthy());
  });
});
