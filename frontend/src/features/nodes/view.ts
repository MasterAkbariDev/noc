import type { PeerView } from "../../api/types";

export const STALE_AFTER_MS = 5 * 60 * 1000;

export function directionLabel(peer: PeerView): string {
  return peer.direction === "serves" ? "Shares its data with this node" : "Its servers are shown here";
}

export function isStale(peer: PeerView, now: number): boolean {
  if (peer.last_seen_at === null) {
    return true;
  }
  return now - Date.parse(peer.last_seen_at) > STALE_AFTER_MS;
}

export function peerStatusText(peer: PeerView, now: number): string {
  if (peer.status === "pending") {
    return "Waiting for the other node to accept the code";
  }
  if (peer.last_error) {
    return `Not reachable: ${peer.last_error}`;
  }
  if (peer.last_seen_at === null) {
    return "Paired, not read yet";
  }
  return isStale(peer, now) ? "Stale: last read a while ago" : "Up to date";
}
