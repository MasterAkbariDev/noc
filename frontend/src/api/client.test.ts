import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiError,
  apiPost,
  decideOnAction,
  changePassword,
  createUser,
  disableUser,
  fetchStreamTicket,
  getActivity,
  getIncident,
  getMe,
  getOverview,
  getServer,
  getStory,
  listIncidents,
  login,
  logout,
  resetUserPassword,
  setUnauthorizedHandler,
  setUserRole,
} from "./client";

const fetchMock = vi.fn<typeof fetch>();

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function expireCookie(name: string): void {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

function sentHeaders(call = 0): Headers {
  return new Headers(fetchMock.mock.calls[call]?.[1]?.headers);
}

beforeEach(() => {
  vi.stubGlobal("fetch", fetchMock);
  document.cookie = "noc_csrf=csrf-value; path=/";
});

afterEach(() => {
  fetchMock.mockReset();
  vi.unstubAllGlobals();
  setUnauthorizedHandler(null);
  expireCookie("noc_csrf");
});

describe("listIncidents", () => {
  it("sends no query when no status is given and never an Authorization header", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    const incidents = await listIncidents();

    expect(incidents).toEqual([]);
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/incidents");
    expect(init?.credentials).toBe("same-origin");
    expect(sentHeaders().has("Authorization")).toBe(false);
  });

  it("adds the status filter as a query parameter", async () => {
    fetchMock.mockResolvedValue(jsonResponse([]));

    await listIncidents("ESCALATED");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/incidents?status=ESCALATED");
  });
});

describe("getIncident", () => {
  it("requests one incident by id", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "abc" }));

    const detail = await getIncident("abc");

    expect(detail).toEqual({ id: "abc" });
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/incidents/abc");
  });
});

describe("apiPost", () => {
  it("sends the body as JSON and the CSRF token from the cookie", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }));

    const result = await apiPost("/api/example", { note: "done" });

    expect(result).toEqual({ ok: true });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/example");
    expect(init?.method).toBe("POST");
    const headers = sentHeaders();
    expect(headers.get("Content-Type")).toBe("application/json");
    expect(headers.get("X-CSRF-Token")).toBe("csrf-value");
    expect(headers.has("Authorization")).toBe(false);
    expect(init?.body).toBe(JSON.stringify({ note: "done" }));
  });

  it("turns a failed POST into an ApiError with the status text when the body has no detail", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 409, statusText: "Conflict" }));

    const failure = await apiPost("/api/example", {}).catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(409);
    expect((failure as ApiError).detail).toBe("409 Conflict");
  });

  it("reads the detail from the JSON body of an error", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ detail: "too many attempts, try again later" }, 429));

    const failure = await apiPost("/api/example", {}).catch((error: unknown) => error);

    expect((failure as ApiError).detail).toBe("too many attempts, try again later");
    expect((failure as ApiError).message).toBe("too many attempts, try again later");
  });

  it("sends no CSRF header on a GET", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ verdict: { level: "ok", sentence: "ok" } }));

    await getOverview();

    expect(sentHeaders().has("X-CSRF-Token")).toBe(false);
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("GET");
  });
});

describe("fetchStreamTicket", () => {
  it("posts with the CSRF header and returns only the ticket string", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ ticket: "one-time", expires_in: 30 }));

    const ticket = await fetchStreamTicket();

    expect(ticket).toBe("one-time");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/events/ticket");
    expect(init?.method).toBe("POST");
    expect(sentHeaders().get("X-CSRF-Token")).toBe("csrf-value");
    expect(sentHeaders().has("Authorization")).toBe(false);
  });
});

describe("error handling", () => {
  it("turns a 401 into an ApiError with the status", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 401, statusText: "Unauthorized" }));

    const failure = await listIncidents().catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(401);
  });

  it("calls the unauthorized handler when a data request gets a 401", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "unauthorized" }, 401));

    await listIncidents().catch(() => undefined);

    expect(handler).toHaveBeenCalledTimes(1);
  });

  it("does not call the unauthorized handler for the login or the me probe", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "invalid username or password" }, 401));

    await login("alice", "wrong-password-here").catch(() => undefined);
    await getMe().catch(() => undefined);

    expect(handler).not.toHaveBeenCalled();
  });

  it("does not end the session when the current password is wrong", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "current password is wrong" }, 401));

    const failure = await changePassword("wrong-password-here", "new-password-here").catch(
      (error: unknown) => error,
    );

    expect((failure as ApiError).detail).toBe("current password is wrong");
    expect(handler).not.toHaveBeenCalled();
  });

  it("does not call the unauthorized handler for other errors", async () => {
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    fetchMock.mockResolvedValue(jsonResponse({ detail: "not found" }, 404));

    await getIncident("missing").catch(() => undefined);

    expect(handler).not.toHaveBeenCalled();
  });
});

describe("session functions", () => {
  it("logs in with a JSON body and returns the signed-in user", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ username: "alice", role: "operator", via: "session" }));

    const me = await login("alice", "a-long-password");

    expect(me).toEqual({ username: "alice", role: "operator", via: "session" });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/auth/login");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ username: "alice", password: "a-long-password" }));
  });

  it("returns nothing for a 204 logout and still sends the CSRF header", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    const result = await logout();

    expect(result).toBeUndefined();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/logout");
    expect(sentHeaders().get("X-CSRF-Token")).toBe("csrf-value");
  });

  it("reads the current user from the me route with cookies only", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ username: "alice", role: "viewer", via: "session" }));

    await getMe();

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/auth/me");
    expect(init?.method).toBe("GET");
    expect(sentHeaders().has("Authorization")).toBe(false);
  });

  it("sends the password change under the field names the server expects", async () => {
    fetchMock.mockResolvedValue(new Response(null, { status: 204 }));

    await changePassword("old-password-here", "new-password-here");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/auth/password");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(
      JSON.stringify({ current_password: "old-password-here", new_password: "new-password-here" }),
    );
  });
});

describe("v2 read functions", () => {
  it("reads the overview without any token", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ verdict: { level: "ok", sentence: "ok" } }));

    await getOverview();

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/overview");
    expect(init?.method).toBe("GET");
    expect(sentHeaders().has("Authorization")).toBe(false);
  });

  it("encodes the incident id in the story path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "a/b" }));

    await getStory("a/b");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/incidents/a%2Fb/story");
  });

  it("encodes the server id in the server path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "srv" }));

    await getServer("srv 1");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/servers/srv%201");
  });

  it("sends only the activity filters that are set", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], next_before_id: null }));

    await getActivity({ limit: 20, action: "login_failed" });

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/activity?limit=20&action=login_failed");
  });

  it("requests the plain activity list without a query when no filter is given", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ items: [], next_before_id: null }));

    await getActivity();

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/activity");
  });
});

describe("v2 user functions", () => {
  it("creates a user with a JSON body", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await createUser({ username: "bob", password: "long-enough-pw", role: "viewer" });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/users");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ username: "bob", password: "long-enough-pw", role: "viewer" }));
  });

  it("changes a role on the user's own path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await setUserRole("u1", "operator");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/users/u1/role");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ role: "operator" }));
  });

  it("disables a user with a POST to the disable path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await disableUser("u1");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/users/u1/disable");
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("POST");
  });

  it("sends the new password under new_password", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ id: "u1" }));

    await resetUserPassword("u1", "another-long-pw");

    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/users/u1/password");
    expect(fetchMock.mock.calls[0]?.[1]?.body).toBe(JSON.stringify({ new_password: "another-long-pw" }));
  });
});

describe("decideOnAction", () => {
  it("posts the decision with the hash unchanged and the CSRF header", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ approval_id: "a1", incident_status: "REMEDIATING" }));
    const hash = "a".repeat(64);

    const result = await decideOnAction("inc-1", "act-1", { decision: "approved", action_hash: hash, comment: null });

    expect(result).toEqual({ approval_id: "a1", incident_status: "REMEDIATING" });
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/incidents/inc-1/actions/act-1/decision");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(JSON.stringify({ decision: "approved", action_hash: hash, comment: null }));
    expect(sentHeaders().get("X-CSRF-Token")).toBe("csrf-value");
  });

  it("sends no decided_by field and encodes both ids in the path", async () => {
    fetchMock.mockResolvedValue(jsonResponse({ approval_id: "a1", incident_status: "REMEDIATING" }));

    await decideOnAction("inc/1", "act 1", { decision: "rejected", action_hash: "b".repeat(64), comment: "no" });

    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/incidents/inc%2F1/actions/act%201/decision");
    expect(String(init?.body)).not.toContain("decided_by");
  });
});
