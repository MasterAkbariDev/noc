import { Link } from "react-router";
import type { ServerSummary } from "../../api/types";
import { cx } from "../../lib/cx";
import { EmptyState, List, ListItem, StatusDot } from "../../ui";
import { serverStatusView } from "../servers/serverView";

function busiestReading(server: ServerSummary): string {
  const metrics = server.metrics;
  if (metrics === null) {
    return "No readings yet";
  }
  const readings = [
    { name: "CPU", value: metrics.cpu_percent },
    { name: "memory", value: metrics.memory_percent },
    { name: "disk", value: metrics.disk_percent },
  ].filter((reading): reading is { name: string; value: number } => reading.value !== null);
  if (readings.length === 0) {
    return "No readings yet";
  }
  const busiest = readings.reduce((top, reading) => (reading.value > top.value ? reading : top));
  return `Busiest: ${busiest.name} ${Math.round(busiest.value)} %`;
}

function incidentsText(count: number): string | null {
  if (count === 0) {
    return null;
  }
  return count === 1 ? "1 open incident" : `${count} open incidents`;
}

export function ServerStrip({ servers }: { servers: ServerSummary[] }) {
  if (servers.length === 0) {
    return <EmptyState title="No servers yet." text="Add a server with the noc command line and it shows up here." />;
  }
  return (
    <List variant="divided" label="Servers">
      {servers.map((server) => {
        const view = serverStatusView(server.status);
        const open = incidentsText(server.open_incidents);
        return (
          <ListItem key={server.id}>
            <Link to={`/servers/${encodeURIComponent(server.id)}`} className="group grid gap-0.5 rounded-control">
              <span className="flex items-center justify-between gap-3">
                <span className="font-semibold group-hover:text-accent group-hover:underline">{server.name}</span>
                <StatusDot tone={view.tone} label={view.label} showLabel />
              </span>
              <span className={cx("text-sm", open === null ? "text-muted" : "text-fg")}>
                {open ?? busiestReading(server)}
                {server.halted && ", automatic fixes paused"}
              </span>
            </Link>
          </ListItem>
        );
      })}
    </List>
  );
}
