import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter, Route, Routes, useLocation } from "react-router";
import { SessionProvider } from "../auth/session";
import { LoginPage } from "./LoginPage";

const fetchMock = vi.fn<typeof fetch>();

const USERNAME = "alice";
const PASSWORD = "a-long-password";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function LocationProbe() {
  const location = useLocation();
  return <p data-testid="location">{`${location.pathname}${location.search}`}</p>;
}

function serve(me: Response, login?: Response | Error) {
  fetchMock.mockImplementation(async (input) => {
    const url = String(input);
    if (url === "/api/auth/me") {
      return me.clone();
    }
    if (url === "/api/auth/login") {
      if (login instanceof Error) {
        throw login;
      }
      return (login ?? jsonResponse({ detail: "unexpected" }, 500)).clone();
    }
    return jsonResponse({ detail: "not found" }, 404);
  });
}

function renderLogin(path: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <SessionProvider>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route path="/" element={<p>Home page</p>} />
            <Route path="/incidents" element={<p>Incidents page</p>} />
          </Routes>
        </SessionProvider>
        <LocationProbe />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function fillAndSubmit(username: string, password: string) {
  fireEvent.change(screen.getByLabelText("Username"), { target: { value: username } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Sign in" }));
}

const ANONYMOUS = jsonResponse({ detail: "unauthorized" }, 401);
const SIGNED_IN = jsonResponse({ username: USERNAME, role: "operator", via: "session" });

beforeEach(() => {
  fetchMock.mockReset();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("LoginPage errors", () => {
  it("names the page Sign in in the document title", async () => {
    serve(ANONYMOUS);
    renderLogin("/login");

    await screen.findByRole("heading", { level: 1, name: "Sign in" });
    expect(document.title).toBe("Sign in · NOC");
  });

  it("says the username or password is wrong for a 401 and clears the password", async () => {
    serve(ANONYMOUS, jsonResponse({ detail: "invalid username or password" }, 401));
    renderLogin("/login");
    await screen.findByRole("heading", { level: 1, name: "Sign in" });

    fillAndSubmit(USERNAME, PASSWORD);

    expect((await screen.findByRole("alert")).textContent).toBe("Invalid username or password.");
    expect((screen.getByLabelText("Password") as HTMLInputElement).value).toBe("");
  });

  it("asks the user to wait for a 429", async () => {
    serve(ANONYMOUS, jsonResponse({ detail: "too many attempts, try again later" }, 429));
    renderLogin("/login");
    await screen.findByRole("heading", { level: 1, name: "Sign in" });

    fillAndSubmit(USERNAME, PASSWORD);

    expect((await screen.findByRole("alert")).textContent).toBe(
      "Too many attempts. Wait 15 minutes and try again.",
    );
  });

  it("says the NOC could not be reached when the request fails", async () => {
    serve(ANONYMOUS, new TypeError("Failed to fetch"));
    renderLogin("/login");
    await screen.findByRole("heading", { level: 1, name: "Sign in" });

    fillAndSubmit(USERNAME, PASSWORD);

    expect((await screen.findByRole("alert")).textContent).toBe("Could not reach the NOC. Try again.");
  });

  it("explains an expired session when the URL says so", async () => {
    serve(ANONYMOUS);
    renderLogin("/login?expired=1");

    expect(await screen.findByText("Your session expired. Sign in again.")).toBeTruthy();
  });
});

describe("LoginPage success", () => {
  it("goes to the requested page and keeps the password out of the URL and browser storage", async () => {
    serve(ANONYMOUS, SIGNED_IN);
    renderLogin("/login?next=%2Fincidents%3Fstatus%3DNEW");
    await screen.findByRole("heading", { level: 1, name: "Sign in" });

    fillAndSubmit(USERNAME, PASSWORD);

    expect(await screen.findByText("Incidents page")).toBeTruthy();
    expect(screen.getByTestId("location").textContent).toBe("/incidents?status=NEW");
    expect(screen.getByTestId("location").textContent).not.toContain(PASSWORD);
    expect(localStorage.length + sessionStorage.length).toBe(0);
    const loginCall = fetchMock.mock.calls.find(([url]) => String(url) === "/api/auth/login");
    expect(loginCall?.[1]?.body).toBe(JSON.stringify({ username: USERNAME, password: PASSWORD }));
    expect(new Headers(loginCall?.[1]?.headers).has("Authorization")).toBe(false);
  });

  it("sends a signed-in visitor straight to the page they asked for", async () => {
    serve(SIGNED_IN);
    renderLogin("/login?next=%2Fincidents");

    expect(await screen.findByText("Incidents page")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/incidents"));
  });

  it("falls back to the overview when the next path points off the site", async () => {
    serve(SIGNED_IN);
    renderLogin("/login?next=%2F%2Fevil.example");

    expect(await screen.findByText("Home page")).toBeTruthy();
    await waitFor(() => expect(screen.getByTestId("location").textContent).toBe("/"));
  });
});
