import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiPost,
  createUser,
  disableUser,
  fetchStreamTicket,
  getActivity,
  getIncident,
  getOverview,
  getServer,
  getStory,
  listIncidents,
  resetUserPassword,
  setUserRole,
} from "./client";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("listIncidents", () => {
  it("sends the bearer token and no query when no status is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    const incidents = await listIncidents("secret-token");

    expect(incidents).toEqual([]);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/incidents");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret-token");
  });

  it("adds the status filter as a query parameter", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listIncidents("t", "ESCALATED");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/incidents?status=ESCALATED");
  });
});

describe("getIncident", () => {
  it("requests one incident by id", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "abc" }));

    const detail = await getIncident("t", "abc");

    expect(detail).toEqual({ id: "abc" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/incidents/abc");
  });
});

describe("apiPost", () => {
  it("sends the bearer token and the body as JSON", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    const result = await apiPost("/api/example", "secret-token", { note: "done" });

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/example");
    expect(init?.method).toBe("POST");
    const headers = new Headers(init?.headers);
    expect(headers.get("Authorization")).toBe("Bearer secret-token");
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(init?.body).toBe(JSON.stringify({ note: "done" }));
  });

  it("turns a failed POST into an ApiError", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 409, statusText: "Conflict" }));

    const failure = await apiPost("/api/example", "t", {}).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(409);
  });
});

describe("fetchStreamTicket", () => {
  it("posts with the bearer token and returns only the ticket string", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ticket: "one-time", expires_in: 30 }));

    const ticket = await fetchStreamTicket("secret-token");

    expect(ticket).toBe("one-time");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/events/ticket");
    expect(init?.method).toBe("POST");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret-token");
  });
});

describe("error handling", () => {
  it("turns a 401 into an ApiError with the status", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 401, statusText: "Unauthorized" }));

    const failure = await listIncidents("wrong").catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(401);
  });
});

describe("v2 read functions", () => {
  it("reads the overview with the bearer token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ verdict: { level: "ok", sentence: "ok" } }));

    await getOverview("secret-token");

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/overview");
    expect(init?.method).toBe("GET");
    expect(new Headers(init?.headers).get("Authorization")).toBe("Bearer secret-token");
  });

  it("encodes the incident id in the story path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "a/b" }));

    await getStory("t", "a/b");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/incidents/a%2Fb/story");
  });

  it("encodes the server id in the server path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "srv" }));

    await getServer("t", "srv 1");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/servers/srv%201");
  });

  it("sends only the activity filters that are set", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], next_before_id: null }));

    await getActivity("t", { limit: 20, action: "login_failed" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/activity?limit=20&action=login_failed");
  });

  it("requests the plain activity list without a query when no filter is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], next_before_id: null }));

    await getActivity("t");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/activity");
  });
});

describe("v2 user functions", () => {
  it("creates a user with a JSON body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await createUser("t", { username: "bob", password: "long-enough-pw", role: "viewer" });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/users");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ username: "bob", password: "long-enough-pw", role: "viewer" }));
  });

  it("changes a role on the user's own path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await setUserRole("t", "u1", "operator");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/users/u1/role");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ role: "operator" }));
  });

  it("disables a user with a POST to the disable path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await disableUser("t", "u1");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/users/u1/disable");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("sends the new password under new_password", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await resetUserPassword("t", "u1", "another-long-pw");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/users/u1/password");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ new_password: "another-long-pw" }));
  });
});
