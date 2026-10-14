import { Server } from "lucide-react";
import { Link } from "react-router";
import type { ServerSummary } from "../../api/types";
import { Badge, EmptyState, StatusDot } from "../../ui";
import { serverLabel, serverTone } from "./model";

export function ServerList({ servers }: { servers: ServerSummary[] }) {
  if (servers.length === 0) {
    return <EmptyState icon={Server} title="No servers yet." />;
  }
  return (
    <ul className="m-0 grid list-none gap-3 p-0">
      {servers.map((server) => (
        <li key={server.id} className="grid gap-1">
          <div className="flex flex-wrap items-center gap-2">
            <StatusDot tone={serverTone(server.status)} label={serverLabel(server.status)} showLabel />
            <Link
              to={`/servers/${encodeURIComponent(server.id)}`}
              className="min-w-0 break-words font-semibold underline underline-offset-4"
            >
              {server.name}
            </Link>
            <Badge tone={server.environment === "prod" ? "warning" : "neutral"}>{server.environment}</Badge>
          </div>
          <p className="m-0 text-sm text-muted">{server.headline}</p>
        </li>
      ))}
    </ul>
  );
}
