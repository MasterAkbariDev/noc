import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  incidentIdFrom,
  LIVE_POLL_MS,
  STREAM_RETRY_MIN_MS,
  StreamConnectedContext,
  useEventStream,
  useLivePollInterval,
} from "./useEventStream";

const INCIDENT_ID = "11111111-1111-1111-1111-111111111111";

class FakeEventSource {
  static instances: FakeEventSource[] = [];

  readonly url: string;
  closed = false;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  private readonly listeners = new Map<string, (event: MessageEvent) => void>();

  constructor(url: string) {
    this.url = url;
    FakeEventSource.instances.push(this);
  }

  addEventListener(type: string, listener: (event: MessageEvent) => void): void {
    this.listeners.set(type, listener);
  }

  close(): void {
    this.closed = true;
  }

  open(): void {
    this.onopen?.();
  }

  fail(): void {
    this.onerror?.();
  }

  message(type: string, data: string): void {
    this.listeners.get(type)?.(new MessageEvent(type, { data }));
  }
}

const fetchMock = vi.fn<typeof fetch>();
let ticketCount = 0;
let queryClient: QueryClient;

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
}

function wrapper({ children }: { children: ReactNode }) {
  return createElement(QueryClientProvider, { client: queryClient }, children);
}

function renderStream(enabled: boolean) {
  return renderHook((current: boolean) => useEventStream(current), {
    wrapper,
    initialProps: enabled,
  });
}

function currentSource(): FakeEventSource {
  const source = FakeEventSource.instances[FakeEventSource.instances.length - 1];
  if (source === undefined) {
    throw new Error("no EventSource was created");
  }
  return source;
}

beforeEach(() => {
  ticketCount = 0;
  fetchMock.mockImplementation(async () => {
    ticketCount += 1;
    return jsonResponse({ ticket: `ticket-${ticketCount}`, expires_in: 30 });
  });
  FakeEventSource.instances = [];
  vi.stubGlobal("fetch", fetchMock);
  vi.stubGlobal("EventSource", FakeEventSource);
  queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
});

afterEach(() => {
  cleanup();
  fetchMock.mockReset();
  vi.unstubAllGlobals();
});

describe("useEventStream", () => {
  it("connects nothing while the session is not signed in", async () => {
    renderStream(false);

    await act(async () => {
      await Promise.resolve();
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(FakeEventSource.instances).toHaveLength(0);
  });

  it("gets a ticket with the session and opens the stream with the ticket, never a bearer header", async () => {
    const { result } = renderStream(true);

    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    const source = currentSource();
    expect(fetchMock.mock.calls[0]?.[0]).toBe("/api/events/ticket");
    expect(new Headers(fetchMock.mock.calls[0]?.[1]?.headers).has("Authorization")).toBe(false);
    expect(source.url).toBe("/api/events/stream?ticket=ticket-1");
    expect(result.current).toBe(false);

    act(() => source.open());

    expect(result.current).toBe(true);
  });

  it("invalidates the incident, detail and trace keys when an event arrives", async () => {
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    renderStream(true);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    const message = JSON.stringify({
      incident_id: INCIDENT_ID,
      id: 7,
      ts: "2026-10-12T10:00:00Z",
      type: "status_changed",
      actor: "orchestrator",
      payload: {},
    });
    act(() => currentSource().message("incident_event", message));

    expect(invalidate.mock.calls.map(([filters]) => filters?.queryKey)).toEqual([
      ["incidents"],
      ["incident", INCIDENT_ID],
      ["trace", INCIDENT_ID],
      ["story", INCIDENT_ID],
      ["overview"],
    ]);
  });

  it("ignores a message that is not an incident event", async () => {
    const invalidate = vi.spyOn(queryClient, "invalidateQueries");
    renderStream(true);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));

    act(() => currentSource().message("incident_event", "not json"));

    expect(invalidate).not.toHaveBeenCalled();
  });

  it("closes after an error and asks for a new ticket after the backoff", async () => {
    const { result } = renderStream(true);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const first = currentSource();
    act(() => first.open());

    act(() => first.fail());

    expect(first.closed).toBe(true);
    expect(result.current).toBe(false);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(2), {
      timeout: STREAM_RETRY_MIN_MS + 2000,
    });
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(currentSource().url).toBe("/api/events/stream?ticket=ticket-2");
  });

  it("closes the stream on unmount", async () => {
    const { unmount } = renderStream(true);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = currentSource();

    unmount();

    expect(source.closed).toBe(true);
  });

  it("closes the stream when the session ends", async () => {
    const { rerender } = renderStream(true);
    await waitFor(() => expect(FakeEventSource.instances).toHaveLength(1));
    const source = currentSource();

    rerender(false);

    expect(source.closed).toBe(true);
  });
});

describe("useLivePollInterval", () => {
  function pollIntervalWith(connected: boolean) {
    return renderHook(() => useLivePollInterval(), {
      wrapper: ({ children }: { children: ReactNode }) =>
        createElement(StreamConnectedContext.Provider, { value: connected }, children),
    });
  }

  it("polls while the stream is not connected", () => {
    expect(pollIntervalWith(false).result.current).toBe(LIVE_POLL_MS);
  });

  it("does not poll while the stream is connected", () => {
    expect(pollIntervalWith(true).result.current).toBe(false);
  });
});

describe("incidentIdFrom", () => {
  it("reads the incident id from a valid message", () => {
    expect(incidentIdFrom(JSON.stringify({ incident_id: INCIDENT_ID }))).toBe(INCIDENT_ID);
  });

  it("returns null for anything else", () => {
    expect(incidentIdFrom("not json")).toBeNull();
    expect(incidentIdFrom(JSON.stringify({ id: 1 }))).toBeNull();
    expect(incidentIdFrom(JSON.stringify({ incident_id: 5 }))).toBeNull();
    expect(incidentIdFrom(JSON.stringify(null))).toBeNull();
    expect(incidentIdFrom(undefined)).toBeNull();
  });
});
