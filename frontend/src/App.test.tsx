import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { MemoryRouter, useLocation } from "react-router";
import { App } from "./App";
import { TokenProvider } from "./auth/token";
import { Toaster, TooltipProvider } from "./ui";

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
          <TokenProvider>
            <MemoryRouter initialEntries={[path]}>
              <App />
              <LocationProbe />
            </MemoryRouter>
          </TokenProvider>
        </Toaster>
      </TooltipProvider>
    </QueryClientProvider>,
  );
}

function currentLocation(): string | null {
  return screen.getByTestId("location").textContent;
}

beforeEach(() => {
  sessionStorage.clear();
  document.title = "NOC";
});

afterEach(() => {
  cleanup();
});

describe("App routes", () => {
  it("shows the overview at the root with its document title", () => {
    renderAt("/");

    expect(screen.getByRole("heading", { level: 1, name: "Overview" })).toBeTruthy();
    expect(document.title).toBe("Overview · NOC");
  });

  it("redirects the old targets page to servers", () => {
    renderAt("/targets");

    expect(currentLocation()).toBe("/servers");
    expect(screen.getByRole("heading", { level: 1, name: "Servers" })).toBeTruthy();
  });

  it("redirects the old trace page to the activity tab of the incident", () => {
    renderAt("/incidents/abc/trace");

    expect(currentLocation()).toBe("/incidents/abc?tab=activity");
  });

  it("shows the server page for a server id", () => {
    renderAt("/servers/abc");

    expect(screen.getByRole("heading", { level: 1, name: "Server" })).toBeTruthy();
  });

  it("shows a not found page for an unknown path", () => {
    renderAt("/no-such-page");

    expect(screen.getByRole("heading", { level: 1, name: "Page not found" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Back to overview" }).getAttribute("href")).toBe("/");
  });

  it("offers a skip link to the main content", () => {
    renderAt("/");

    expect(screen.getByRole("link", { name: "Skip to content" }).getAttribute("href")).toBe("#main");
    expect(document.getElementById("main")).not.toBeNull();
  });
});
