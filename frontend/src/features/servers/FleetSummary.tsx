import { CircleOff, Server, ServerCrash, Siren } from "lucide-react";
import type { ServerSummary } from "../../api/types";
import { KpiTile } from "../../ui";

export type FleetCounts = { total: number; up: number; down: number; openIncidents: number; halted: number };

export function fleetCounts(servers: ServerSummary[]): FleetCounts {
  return {
    total: servers.length,
    up: servers.filter((server) => server.status === "up").length,
    down: servers.filter((server) => server.status === "down").length,
    openIncidents: servers.reduce((sum, server) => sum + server.open_incidents, 0),
    halted: servers.filter((server) => server.halted).length,
  };
}

export function FleetSummary({ servers }: { servers: ServerSummary[] }) {
  const counts = fleetCounts(servers);
  return (
    <section aria-label="Fleet summary" className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <KpiTile label="Servers" value={counts.total} hint={`${counts.up} reachable now`} icon={Server} tone={counts.up === counts.total ? "ok" : "neutral"} />
      <KpiTile
        label="Not reachable"
        value={counts.down}
        hint="Prometheus cannot scrape them"
        icon={ServerCrash}
        tone={counts.down > 0 ? "critical" : "ok"}
      />
      <KpiTile
        label="Open incidents"
        value={counts.openIncidents}
        hint="Across every server"
        icon={Siren}
        tone={counts.openIncidents > 0 ? "warning" : "ok"}
        to="/incidents?filter=open"
      />
      <KpiTile
        label="Automation halted"
        value={counts.halted}
        hint="Servers where the NOC only watches"
        icon={CircleOff}
        tone={counts.halted > 0 ? "warning" : "neutral"}
      />
    </section>
  );
}
