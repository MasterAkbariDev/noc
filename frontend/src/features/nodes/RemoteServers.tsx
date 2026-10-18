import { useMutation, useQueryClient } from "@tanstack/react-query";
import { refreshPeer, setPeerServerAutomation } from "../../api/client";
import type { IncidentSummary, PeerView, ServerSummary } from "../../api/types";
import { useSession } from "../../auth/session";
import { Field, Select } from "../../ui/Form";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";
import { MODE_OPTIONS } from "../servers/ServerAdmin";
import { EndpointCard } from "../servers/EndpointCard";
import { ServerCard } from "../servers/ServerCard";
import { PEERS_KEY, usePeersQuery } from "./queries";
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

// Admins can change a remote server's mode here. The owning NOC applies it and
// this panel reads the new status back straight away.
function RemoteModeControl({ peer, server }: { peer: PeerView; server: ServerSummary }) {
  const { me } = useSession();
  const queryClient = useQueryClient();
  const toast = useToast();
  const mode = useMutation({
    mutationFn: async (level: string) => {
      await setPeerServerAutomation(peer.id, server.name, level);
      return refreshPeer(peer.id);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [PEERS_KEY] });
      toast.success(`Mode of ${server.name} saved on ${peer.last_status?.node_name ?? peer.name}.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  if (me.role !== "admin") {
    return null;
  }
  return (
    <Field label="Mode">
      <Select
        aria-label={`Mode of ${server.name} on ${peer.last_status?.node_name ?? peer.name}`}
        compact
        value={server.automation_level}
        disabled={mode.isPending}
        options={MODE_OPTIONS}
        onChange={(event) => mode.mutate(event.target.value)}
      />
    </Field>
  );
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
      {servers.length === 0 && (snapshot?.endpoints ?? []).length === 0 ? (
        <p className="m-0 text-sm text-muted">This node reports no servers yet.</p>
      ) : (
        <ul aria-label="Server cards" className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 xl:grid-cols-3">
          {servers.map((server) => (
            <li key={server.id} className="grid min-w-0 gap-2">
              <ServerCard server={server} readOnly />
              <RemoteModeControl peer={peer} server={server} />
            </li>
          ))}
          {(snapshot?.endpoints ?? []).map((endpoint) => (
            <li key={`endpoint-${endpoint.name}`} className="min-w-0">
              <EndpointCard endpoint={endpoint} node={snapshot?.node_name} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
