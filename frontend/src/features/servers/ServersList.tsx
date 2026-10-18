import { Server } from "lucide-react";
import type { ServerSummary } from "../../api/types";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { List, ListItem } from "../../ui/List";
import { Skeleton } from "../../ui/Skeleton";
import { getEndpoints } from "../../api/client";
import { useQuery } from "@tanstack/react-query";
import { RemoteNodeGroup, useFollowedPeers } from "../nodes/RemoteServers";
import { EndpointCard } from "./EndpointCard";
import { FleetSummary } from "./FleetSummary";
import { ServerCard } from "./ServerCard";
import { useServersQuery } from "./queries";
import { errorText } from "./serverView";

const PANEL_TAG = "panel host";

export function groupServers(servers: ServerSummary[]): { heading: string; servers: ServerSummary[] }[] {
  const panel = servers.filter((server) => server.tag === PANEL_TAG);
  const rest = servers.filter((server) => server.tag !== PANEL_TAG);
  const groups: { heading: string; servers: ServerSummary[] }[] = [];
  if (panel.length > 0) {
    groups.push({ heading: "Panel host", servers: panel });
  }
  if (rest.length > 0) {
    groups.push({ heading: panel.length > 0 ? "Other servers" : "Servers", servers: rest });
  }
  return groups;
}

export function ServersList() {
  const query = useServersQuery();
  const followed = useFollowedPeers();
  const endpoints = useQuery({ queryKey: ["endpoints"], queryFn: getEndpoints, refetchInterval: 30_000 });

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
  return (
    <div className="grid gap-8">
      <FleetSummary servers={query.data} />
      {groupServers(query.data).map((group) => (
        <section key={group.heading} aria-label={group.heading} className="grid gap-3">
          <h3 className="m-0 text-base font-semibold">{group.heading}</h3>
          <List label="Server cards" gap="lg" className="sm:grid-cols-2 xl:grid-cols-3">
            {group.servers.map((server) => (
              <ListItem key={server.id} className="min-w-0">
                <ServerCard server={server} />
              </ListItem>
            ))}
          </List>
        </section>
      ))}
      {endpoints.isSuccess && endpoints.data.length > 0 && (
        <section aria-label="Servers without NOC" className="grid gap-3">
          <h3 className="m-0 text-base font-semibold">Servers without NOC</h3>
          <ul aria-label="Server without NOC cards" className="m-0 grid list-none gap-4 p-0 sm:grid-cols-2 xl:grid-cols-3">
            {endpoints.data.map((endpoint) => (
              <li key={endpoint.id} className="min-w-0">
                <EndpointCard endpoint={endpoint} />
              </li>
            ))}
          </ul>
        </section>
      )}
      {followed.map((peer) => (
        <RemoteNodeGroup key={peer.id} peer={peer} />
      ))}
    </div>
  );
}
