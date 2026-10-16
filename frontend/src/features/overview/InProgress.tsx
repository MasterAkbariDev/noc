import { useQuery } from "@tanstack/react-query";
import { listIncidents } from "../../api/client";
import type { IncidentSummary } from "../../api/types";
import { errorMessage } from "../../lib/format";
import { incidentStatusView } from "../../lib/tones";
import { AnimatedList, ErrorState, RelativeTime, Skeleton } from "../../ui";
import { IncidentLink } from "../incident/IncidentLink";
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
    return <p className="m-0 text-muted">Nothing else is in progress right now.</p>;
  }
  return <AnimatedList items={rows} itemKey={rowKey} label="In progress" className="gap-1" render={(incident) => <InProgressRow incident={incident} />} />;
}

const rowKey = (incident: IncidentSummary) => incident.id;

function InProgressRow({ incident }: { incident: IncidentSummary }) {
  const view = incidentStatusView(incident.status);
  return (
    <div className="flex items-start gap-4 py-2">
      <span aria-hidden="true" className="mt-2 inline-block size-2.5 shrink-0 rounded-full bg-info step-current" />
      <div className="grid min-w-0 gap-0.5">
        <IncidentLink id={incident.id} className="font-semibold break-words hover:text-accent hover:underline">
          {incident.title}
        </IncidentLink>
        <span className="text-sm text-muted">
          {view.label}, started <RelativeTime iso={incident.opened_at} />
        </span>
      </div>
    </div>
  );
}
