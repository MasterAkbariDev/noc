import { Server } from "lucide-react";
import { Link } from "react-router";
import type { ServerSummary } from "../../api/types";
import { percentFromHundred } from "../../lib/format";
import { DataTable, EmptyState, Meter, StatusDot, type Column } from "../../ui";
import { EnvironmentBadge, OpenIncidents } from "../servers/ServerParts";
import { isAttention } from "../servers/serverView";
import { serverLabel, serverTone } from "./model";

function UsageCell({ label, server, value }: { label: string; server: string; value: number | null | undefined }) {
  if (value === null || value === undefined) {
    return <span className="text-xs text-muted">No data</span>;
  }
  const text = percentFromHundred(value);
  return (
    <span className="grid min-w-20 gap-1">
      <span className="text-xs font-semibold tabular-nums">{text}</span>
      <Meter label={`${label} on ${server}`} value={value} valueText={text} tone={isAttention(value) ? "critical" : "neutral"} size="sm" />
    </span>
  );
}

const COLUMNS: Column<ServerSummary>[] = [
  {
    key: "server",
    header: "Server",
    cell: (server) => (
      <span className="grid gap-1">
        <Link to={`/servers/${encodeURIComponent(server.id)}`} className="font-semibold break-words hover:text-accent hover:underline">
          {server.name}
        </Link>
        <span className="flex flex-wrap items-center gap-2 text-xs">
          <StatusDot tone={serverTone(server.status)} label={serverLabel(server.status)} showLabel />
          <EnvironmentBadge environment={server.environment} />
        </span>
      </span>
    ),
  },
  { key: "cpu", header: "CPU", cell: (server) => <UsageCell label="CPU" server={server.name} value={server.metrics?.cpu_percent} /> },
  {
    key: "memory",
    header: "Memory",
    cell: (server) => <UsageCell label="Memory" server={server.name} value={server.metrics?.memory_percent} />,
  },
  { key: "disk", header: "Disk", cell: (server) => <UsageCell label="Disk" server={server.name} value={server.metrics?.disk_percent} /> },
  {
    key: "incidents",
    header: "Incidents",
    cell: (server) => <OpenIncidents count={server.open_incidents} worstSeverity={server.worst_severity} />,
  },
];

export function ServerResources({ servers }: { servers: ServerSummary[] }) {
  if (servers.length === 0) {
    return <EmptyState icon={Server} title="No servers yet." />;
  }
  return (
    <DataTable
      label="Server resources"
      columns={COLUMNS}
      rows={servers}
      rowKey={(server) => server.id}
      empty="No servers yet."
      framed={false}
      minWidth="lg"
    />
  );
}
