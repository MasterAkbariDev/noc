import { useQuery } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { getEndpoints } from "../../api/client";
import type { EndpointView, PeerView } from "../../api/types";
import { RelativeTime } from "../../ui/RelativeTime";
import { Badge } from "../../ui/Badge";
import { Card } from "../../ui/Card";
import { DataTable, type Column } from "../../ui/DataTable";
import { Disclosure } from "../../ui/Disclosure";
import { Tabs } from "../../ui/Tabs";
import { AddEndpoint, EndpointRow } from "./EndpointsSection";
import { AddNode, CreateToken, PeerRow } from "./NodesAdmin";
import { usePeersQuery } from "./queries";
import { directionLabel, isStale, peerStatusText } from "./view";

const ENDPOINTS_KEY = "endpoints";

function Tile({ label, value, hint }: { label: string; value: number | string; hint: string }) {
  return (
    <Card className="grid gap-1 rounded-card shadow-sm">
      <span className="text-xs font-medium uppercase tracking-wide text-muted">{label}</span>
      <span className="text-3xl font-semibold tabular-nums">{value}</span>
      <span className="text-xs text-muted">{hint}</span>
    </Card>
  );
}

function statusBadge(peer: PeerView, now: number) {
  if (peer.status === "pending") {
    return <Badge tone="warning">Waiting</Badge>;
  }
  if (peer.last_error) {
    return <Badge tone="critical">Unreachable</Badge>;
  }
  if (isStale(peer, now)) {
    return <Badge tone="warning">Stale</Badge>;
  }
  return <Badge tone="ok">Up to date</Badge>;
}

const PEER_COLUMNS: Column<PeerView>[] = [
  {
    key: "name",
    header: "Name",
    cell: (peer) => (
      <div className="grid gap-0.5">
        <span className="font-medium break-all">{peer.name}</span>
        <span className="text-xs text-muted break-all">{peer.url}</span>
      </div>
    ),
  },
  { key: "direction", header: "Direction", cell: (peer) => <span className="text-sm">{directionLabel(peer)}</span> },
  { key: "status", header: "Status", cell: (peer) => statusBadge(peer, Date.now()) },
  {
    key: "read",
    header: "Last read",
    cell: (peer) =>
      peer.last_seen_at ? <RelativeTime iso={peer.last_seen_at} /> : <span className="text-muted">never</span>,
    className: "whitespace-nowrap",
  },
  {
    key: "detail",
    header: "Details",
    cell: (peer) => <span className="text-xs text-muted">{peerStatusText(peer, Date.now())}</span>,
  },
  { key: "actions", header: "", cell: (peer) => <PeerRow peer={peer} />, className: "text-right" },
];

const ENDPOINT_COLUMNS: Column<EndpointView>[] = [
  {
    key: "name",
    header: "Name",
    cell: (endpoint) => (
      <div className="grid gap-0.5">
        <span className="font-medium break-all">{endpoint.name}</span>
        <span className="text-xs text-muted break-all">
          {endpoint.host}:{endpoint.ssh_port}
          {endpoint.url ? ` · ${endpoint.url}` : ""}
        </span>
      </div>
    ),
  },
  {
    key: "ssh",
    header: "SSH",
    cell: (endpoint) =>
      endpoint.last_result === null ? (
        <span className="text-muted">not checked</span>
      ) : endpoint.last_result.ssh.open ? (
        <Badge tone="ok">Answers</Badge>
      ) : (
        <Badge tone="critical">No answer</Badge>
      ),
  },
  {
    key: "web",
    header: "Web",
    cell: (endpoint) =>
      endpoint.last_result?.web === undefined ? (
        <span className="text-muted">—</span>
      ) : endpoint.last_result.web.ok ? (
        <Badge tone="ok">HTTP {endpoint.last_result.web.status}</Badge>
      ) : (
        <Badge tone="critical">Down</Badge>
      ),
  },
  {
    key: "checked",
    header: "Last check",
    cell: (endpoint) =>
      endpoint.last_checked_at ? <RelativeTime iso={endpoint.last_checked_at} /> : <span className="text-muted">never</span>,
    className: "whitespace-nowrap",
  },
  { key: "actions", header: "", cell: (endpoint) => <EndpointRow endpoint={endpoint} />, className: "text-right" },
];

function NocNodesTab({ peers }: { peers: PeerView[] }) {
  return (
    <div className="grid gap-4">
      <div className="grid gap-3 md:grid-cols-2">
        <Disclosure summary="Add a NOC node" hint="Paste the auth token from the other NOC">
          <div className="p-4">
            <AddNode />
          </div>
        </Disclosure>
        <Disclosure summary="Give an auth token to another NOC" hint="Valid for ten minutes, works once">
          <div className="p-4">
            <CreateToken />
          </div>
        </Disclosure>
      </div>
      <DataTable
        label="NOC nodes"
        columns={PEER_COLUMNS}
        rows={peers}
        rowKey={(peer) => peer.id}
        empty="No NOC nodes yet. Add one with an auth token, or create a token for another NOC."
      />
    </div>
  );
}

function EndpointsTab({ endpoints }: { endpoints: EndpointView[] }) {
  return (
    <div className="grid gap-4">
      <Disclosure summary="Add a server without NOC" hint="Checked over the network, nothing is installed">
        <div className="p-4">
          <AddEndpoint />
        </div>
      </Disclosure>
      <DataTable
        label="Servers without NOC"
        columns={ENDPOINT_COLUMNS}
        rows={endpoints}
        rowKey={(endpoint) => endpoint.id}
        empty="No servers without NOC yet."
      />
    </div>
  );
}

export function NodesWorkspace({ ssh }: { ssh: ReactNode }) {
  const peers = usePeersQuery();
  const endpoints = useQuery({ queryKey: [ENDPOINTS_KEY], queryFn: getEndpoints });
  const [tab, setTab] = useState("nodes");
  const nodeList = peers.isSuccess ? peers.data : [];
  const endpointList = endpoints.isSuccess ? endpoints.data : [];
  const paired = nodeList.filter((peer) => peer.status === "paired").length;
  return (
    <div className="grid gap-6">
      <div className="grid gap-3 sm:grid-cols-3">
        <Tile label="NOC nodes" value={paired} hint={`${nodeList.length - paired} waiting`} />
        <Tile label="Servers without NOC" value={endpointList.length} hint="checked over the network" />
        <Tile label="SSH hosts" value="Keys" hint="open the SSH hosts tab" />
      </div>
      <Tabs
        label="Node types"
        value={tab}
        onValueChange={setTab}
        items={[
          { value: "nodes", label: `NOC nodes (${nodeList.length})`, content: <NocNodesTab peers={nodeList} /> },
          {
            value: "endpoints",
            label: `Servers without NOC (${endpointList.length})`,
            content: <EndpointsTab endpoints={endpointList} />,
          },
          { value: "ssh", label: "SSH hosts", content: ssh },
        ]}
      />
    </div>
  );
}
