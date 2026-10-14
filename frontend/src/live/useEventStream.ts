import { useQueryClient, type QueryClient } from "@tanstack/react-query";
import { createContext, useContext, useEffect, useState } from "react";
import { fetchStreamTicket } from "../api/client";

export const STREAM_RETRY_MIN_MS = 2000;
export const STREAM_RETRY_MAX_MS = 30000;
export const LIVE_POLL_MS = 10000;
export const INCIDENT_EVENT_TYPE = "incident_event";

export const StreamConnectedContext = createContext(false);

export function useLivePollInterval(): number | false {
  return useContext(StreamConnectedContext) ? false : LIVE_POLL_MS;
}

export function streamUrl(ticket: string): string {
  return `/api/events/stream?${new URLSearchParams({ ticket })}`;
}

export function incidentIdFrom(data: unknown): string | null {
  if (typeof data !== "string") {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(data);
    if (typeof parsed === "object" && parsed !== null && "incident_id" in parsed) {
      return typeof parsed.incident_id === "string" ? parsed.incident_id : null;
    }
    return null;
  } catch {
    return null;
  }
}

export function invalidateIncident(queryClient: QueryClient, incidentId: string): void {
  void queryClient.invalidateQueries({ queryKey: ["incidents"] });
  void queryClient.invalidateQueries({ queryKey: ["incident", incidentId] });
  void queryClient.invalidateQueries({ queryKey: ["trace", incidentId] });
  void queryClient.invalidateQueries({ queryKey: ["story", incidentId] });
  void queryClient.invalidateQueries({ queryKey: ["overview"] });
}

export function useEventStream(enabled: boolean): boolean {
  const queryClient = useQueryClient();
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    if (!enabled) {
      return;
    }

    let active = true;
    let source: EventSource | null = null;
    let retryTimer: ReturnType<typeof setTimeout> | undefined;
    let delay = STREAM_RETRY_MIN_MS;

    function closeSource(): void {
      source?.close();
      source = null;
    }

    function scheduleRetry(): void {
      setConnected(false);
      closeSource();
      const wait = delay;
      delay = Math.min(delay * 2, STREAM_RETRY_MAX_MS);
      retryTimer = setTimeout(() => void connect(), wait);
    }

    function onIncidentEvent(event: MessageEvent): void {
      const incidentId = incidentIdFrom(event.data);
      if (incidentId !== null) {
        invalidateIncident(queryClient, incidentId);
      }
    }

    async function connect(): Promise<void> {
      try {
        const ticket = await fetchStreamTicket();
        if (!active) {
          return;
        }
        const next = new EventSource(streamUrl(ticket));
        source = next;
        next.onopen = () => {
          delay = STREAM_RETRY_MIN_MS;
          setConnected(true);
        };
        next.addEventListener(INCIDENT_EVENT_TYPE, onIncidentEvent);
        next.onerror = () => {
          if (active) {
            scheduleRetry();
          }
        };
      } catch {
        if (active) {
          scheduleRetry();
        }
      }
    }

    void connect();

    return () => {
      active = false;
      clearTimeout(retryTimer);
      closeSource();
      setConnected(false);
    };
  }, [enabled, queryClient]);

  return connected;
}
