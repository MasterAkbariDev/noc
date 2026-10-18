import { Server } from "lucide-react";
import type { ServerSummary } from "../../api/types";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { List, ListItem } from "../../ui/List";
import { Skeleton } from "../../ui/Skeleton";
import { RemoteServerCard, useFollowedPeers } from "../nodes/RemoteServers";
import { FleetSummary } from "./FleetSummary";
import { ServerCard } from "./ServerCard";
import { SyncTimer } from "./SyncTimer";
import { useServersQuery } from "./queries";
import { errorText } from "./serverView";

export const CURRENT_TAG = "current";

// The server this panel runs on comes first; the rest keep their order.
export function currentFirst(servers: ServerSummary[]): ServerSummary[] {
  return [...servers].sort((a, b) => Number(b.tag === CURRENT_TAG) - Number(a.tag === CURRENT_TAG));
}

export function ServersList() {
  const query = useServersQuery();
  const followed = useFollowedPeers();

  if (query.isPending) {
    return <Skeleton lines={4} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="Could not load the servers"
        message={errorText(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.data.length === 0 && followed.length === 0) {
    return (
      <EmptyState
        icon={Server}
        title="No servers yet"
        text="Servers appear here once the NOC has an inventory for them."
      />
    );
  }
  const cards = [
    ...currentFirst(query.data).map((server) => (
      <ListItem key={`local-${server.id}`} className="min-w-0">
        <ServerCard server={server} />
      </ListItem>
    )),
    ...followed.flatMap((peer) =>
      (peer.last_status?.servers ?? []).map((server) => (
        <ListItem key={`peer-${peer.id}-${server.id}`} className="min-w-0">
          <RemoteServerCard peer={peer} server={server} />
        </ListItem>
      )),
    ),
  ];
  return (
    <div className="grid gap-6">
      <FleetSummary servers={query.data} />
      <SyncTimer />
      <List label="Server cards" gap="lg" className="sm:grid-cols-2 xl:grid-cols-3">
        {cards}
      </List>
    </div>
  );
}
