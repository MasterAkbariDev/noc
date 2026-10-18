import type { IncidentSummary, PeerView } from "../../api/types";
import { ServerCard } from "../servers/ServerCard";
import { usePeersQuery } from "./queries";
import { peerStatusText } from "./view";

export function followedPeers(peers: PeerView[]): PeerView[] {
  return peers.filter((peer) => peer.direction === "follows" && peer.status === "paired");
}

export function useFollowedPeers(): PeerView[] {
  const query = usePeersQuery();
  return query.isSuccess ? followedPeers(query.data) : [];
}

export function remoteIncidents(peers: PeerView[]): IncidentSummary[] {
  return peers.flatMap((peer) => {
    const snapshot = peer.last_status;
    if (snapshot === null) {
      return [];
    }
    return snapshot.incidents.map((incident) => ({
      ...incident,
      confidence: null,
      node: snapshot.node_name,
    }));
  });
}

export function RemoteNodeGroup({ peer }: { peer: PeerView }) {
  const snapshot = peer.last_status;
  const servers = snapshot?.servers ?? [];
  return (
    <section aria-label={`Servers of ${snapshot?.node_name ?? peer.name}`} className="grid gap-3">
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="m-0 text-base font-semibold">{snapshot?.node_name ?? peer.name}</h3>
        <span className="text-xs text-muted">Another NOC · {peerStatusText(peer, Date.now())}</span>
      </header>
      {servers.length === 0 ? (
        <p className="m-0 text-sm text-muted">This node reports no servers yet.</p>
      ) : (
        <ul aria-label="Server cards" className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 xl:grid-cols-3">
          {servers.map((server) => (
            <li key={server.id} className="min-w-0">
              <ServerCard server={server} readOnly />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
