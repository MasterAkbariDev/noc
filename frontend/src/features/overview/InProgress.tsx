import { useQuery } from "@tanstack/react-query";
import { Activity } from "lucide-react";
import { Link } from "react-router";
import { listIncidents } from "../../api/client";
import type { IncidentSummary } from "../../api/types";
import { errorMessage } from "../../lib/format";
import { incidentStatusView } from "../../lib/tones";
import { Badge, buttonClass, EmptyState, ErrorState, RelativeTime, Skeleton } from "../../ui";
import { OVERVIEW_FALLBACK_POLL_MS } from "./model";

export const IN_PROGRESS_KEY = ["overview", "in-progress"] as const;

const IN_PROGRESS_STATUSES: ReadonlySet<string> = new Set([
  "NEW",
  "INVESTIGATING",
  "DIAGNOSED",
  "PLANNED",
  "REMEDIATING",
  "VERIFYING",
]);

export function inProgressIncidents(incidents: IncidentSummary[]): IncidentSummary[] {
  return incidents.filter((incident) => IN_PROGRESS_STATUSES.has(incident.status));
}

export function InProgress() {
  const query = useQuery({
    queryKey: IN_PROGRESS_KEY,
    queryFn: () => listIncidents({ statuses: [...IN_PROGRESS_STATUSES], limit: 50 }),
    refetchInterval: OVERVIEW_FALLBACK_POLL_MS,
  });

  if (query.isPending) {
    return <Skeleton lines={3} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="Incidents in progress could not be loaded."
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const rows = inProgressIncidents(query.data);
  if (rows.length === 0) {
    return <EmptyState icon={Activity} title="Nothing is in progress." />;
  }
  return (
    <ul className="m-0 grid list-none gap-3 p-0">
      {rows.map((incident) => (
        <InProgressRow key={incident.id} incident={incident} />
      ))}
    </ul>
  );
}

function InProgressRow({ incident }: { incident: IncidentSummary }) {
  const view = incidentStatusView(incident.status);
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-control border border-border p-3">
      <Badge tone={view.tone}>{view.label}</Badge>
      <span className="min-w-0 flex-1 break-words font-medium">{incident.title}</span>
      <span className="text-sm text-muted">
        Started <RelativeTime iso={incident.opened_at} />
      </span>
      <Link
        to={`/incidents/${encodeURIComponent(incident.id)}`}
        className={buttonClass({ size: "sm" })}
      >
        Open
      </Link>
    </li>
  );
}
