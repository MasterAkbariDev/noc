import { describe, expect, it } from "vitest";
import type { PeerView } from "../../api/types";
import { isStale, peerStatusText, STALE_AFTER_MS } from "./view";

const NOW = Date.parse("2026-10-17T15:00:00Z");

function peer(changes: Partial<PeerView> = {}): PeerView {
  return {
    id: "p-1",
    name: "node-46",
    url: "https://46.example",
    direction: "follows",
    status: "paired",
    paired_at: "2026-10-17T14:00:00Z",
    expires_at: null,
    last_seen_at: "2026-10-17T14:59:00Z",
    last_error: null,
    last_status: null,
    ...changes,
  };
}

describe("node status", () => {
  it("says a pending pairing is waiting", () => {
    expect(peerStatusText(peer({ status: "pending" }), NOW)).toBe("Waiting for the other node to accept the code");
  });

  it("shows the last error when the other node is unreachable", () => {
    expect(peerStatusText(peer({ last_error: "ConnectTimeout" }), NOW)).toBe("Not reachable: ConnectTimeout");
  });

  it("marks data older than five minutes as stale", () => {
    expect(isStale(peer(), NOW)).toBe(false);
    const old = new Date(NOW - STALE_AFTER_MS - 1000).toISOString();
    expect(isStale(peer({ last_seen_at: old }), NOW)).toBe(true);
    expect(peerStatusText(peer({ last_seen_at: old }), NOW)).toBe("Stale: last read a while ago");
  });

  it("treats a paired node that was never read as stale", () => {
    expect(isStale(peer({ last_seen_at: null }), NOW)).toBe(true);
    expect(peerStatusText(peer({ last_seen_at: null }), NOW)).toBe("Paired, not read yet");
  });
});
