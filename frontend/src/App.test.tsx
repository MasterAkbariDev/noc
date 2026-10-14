import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, useLocation } from "react-router";
import { App } from "./App";
import { SessionProvider } from "./auth/session";
import { Toaster, TooltipProvider } from "./ui";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function serveSession(signedIn: boolean) {
  fetchMock.mockImplementation(async (input) => {
    if (String(input) === "/api/auth/me") {
      return signedIn
        ? jsonResponse({ username: "alice", role: "operator", via: "session" })
        : jsonResponse({ detail: "unauthorized" }, 401);
    }
    return jsonResponse({ detail: "not found" }, 404);
  });
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function renderAt(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <Toaster>
          <MemoryRouter initialEntries={[path]}>
            <SessionProvider>
              <App />
            </SessionProvider>
            <LocationProbe />
          </MemoryRouter>
        </Toaster>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function currentLocation(): string | null {
  return screen.getByTestId("location").textContent;
}

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
  serveSession(true);
  document.title = "NOC";
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("App routes", () => {
  it("shows the overview at the root with its document title", async () => {
    renderAt("/");

    expect(await screen.findByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
    expect(document.title).toBe("Overview · NOC");
  });

  it("redirects the old targets page to servers", async () => {
    renderAt("/targets");

    expect(await screen.findByRole("heading", { level: 1, name: "Servers" })).toBeTruthy();
    expect(currentLocation()).toBe("/servers");
  });

  it("redirects the old trace page to the activity tab of the incident", async () => {
    renderAt("/incidents/abc/trace");

    await waitFor(() => expect(currentLocation()).toBe("/incidents/abc?tab=activity"));
  });

  it("shows the server page for a server id", async () => {
    renderAt("/servers/abc");

    expect(await screen.findByRole("heading", { level: 1, name: "Server" })).toBeTruthy();
  });

  it("shows a not found page for an unknown path", async () => {
    renderAt("/no-such-page");

    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to overview" }).getAttribute("href")).toBe("/");
  });

  it("offers a skip link to the main content", async () => {
    renderAt("/");

    await screen.findByRole("heading", { level: 1, name: "Overview" });
    expect(screen.getByRole("link", { name: "Skip to content" }).getAttribute("href")).toBe("#main");
    expect(document.getElementById("main")).not.toBeNull();
  });
});

describe("login guard", () => {
  it("sends an anonymous visitor to the login page with the path they asked for", async () => {
    serveSession(false);
    renderAt("/incidents?status=NEW");

    await waitFor(() => expect(currentLocation()).toBe("/login?next=%2Fincidents%3Fstatus%3DNEW"));
    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeTruthy();
  });

  it("shows the login page without the app shell", async () => {
    serveSession(false);
    renderAt("/login");

    expect(await screen.findByRole("heading", { level: 1, name: "Sign in" })).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Skip to content" })).toBeNull();
  });

  it("does not open the event stream while anonymous", async () => {
    serveSession(false);
    renderAt("/login");

    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    const ticketRequests = fetchMock.mock.calls.filter(([url]) => String(url) === "/api/events/ticket");
    expect(ticketRequests).toHaveLength(0);
  });
});
