import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, apiPost, fetchStreamTicket, getIncident, listIncidents } from "./client";

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
