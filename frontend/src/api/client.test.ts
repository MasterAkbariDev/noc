import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, getIncident, listIncidents } from "./client";

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

describe("error handling", () => {
  it("turns a 401 into an ApiError with the status", async () => {
    fetchMock.mockResolvedValue(new Response("{}", { status: 401, statusText: "Unauthorized" }));

    const failure = await listIncidents("wrong").catch((error: unknown) => error);

    expect(failure).toBeInstanceOf(ApiError);
    expect((failure as ApiError).status).toBe(401);
  });
});
