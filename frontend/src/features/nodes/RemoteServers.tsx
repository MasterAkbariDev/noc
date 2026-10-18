import { useMutation, useQueryClient } from "@tanstack/react-query";
import { refreshPeer, setPeerServerAutomation } from "../../api/client";
import type { IncidentSummary, PeerView, ServerSummary } from "../../api/types";
import { useSession } from "../../auth/session";
import { Button } from "../../ui/Button";
import { Field, Select } from "../../ui/Form";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";
import { MODE_OPTIONS } from "../servers/ServerAdmin";
import { ServerCard } from "../servers/ServerCard";
import { PEERS_KEY, usePeersQuery } from "./queries";

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

export function nodeNameOf(peer: PeerView): string {
  return peer.last_status?.node_name ?? peer.name;
}

// Mode select and sync button under a server from another NOC. Admins only.
function RemoteFooter({ peer, server }: { peer: PeerView; server: ServerSummary }) {
  const { me } = useSession();
  const queryClient = useQueryClient();
  const toast = useToast();
  const node = nodeNameOf(peer);
  const mode = useMutation({
    mutationFn: async (level: string) => {
      await setPeerServerAutomation(peer.id, server.name, level);
      return refreshPeer(peer.id);
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [PEERS_KEY] });
      toast.success(`Mode of ${server.name} saved on ${node}.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const sync = useMutation({
    mutationFn: () => refreshPeer(peer.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [PEERS_KEY] });
      toast.success(`Synced ${node}.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  if (me.role !== "admin") {
    return null;
  }
  return (
    <div className="grid gap-2 border-t border-border pt-3">
      <Field label="Mode">
        <Select
          aria-label={`Mode of ${server.name} on ${node}`}
          compact
          value={server.automation_level}
          disabled={mode.isPending}
          options={MODE_OPTIONS}
          onChange={(event) => mode.mutate(event.target.value)}
        />
      </Field>
      <div className="flex justify-end">
        <Button size="sm" aria-label={`Sync ${node}`} disabled={sync.isPending} onClick={() => sync.mutate()}>
          Sync now
        </Button>
      </div>
    </div>
  );
}

// One server from another NOC, shown as a normal card. The "current" tag belongs to the
// panel's own server only, so the tag another NOC reports is not shown here.
export function RemoteServerCard({ peer, server }: { peer: PeerView; server: ServerSummary }) {
  return (
    <ServerCard
      server={{ ...server, tag: null }}
      readOnly
      node={nodeNameOf(peer)}
      footer={<RemoteFooter peer={peer} server={server} />}
    />
  );
}

