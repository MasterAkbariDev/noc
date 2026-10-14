import { Link } from "react-router";
import type { StuckIncident } from "../../api/types";
import { IncidentStatusBadge, RelativeTime } from "../../ui";

function JobLine({ incident }: { incident: StuckIncident }) {
  const attempts = incident.job_attempts === null ? "" : `, attempt ${incident.job_attempts}`;
  return (
    <p className="m-0 text-sm">
      Job <code className="text-xs">{incident.job_status ?? "none"}</code>
      {attempts}
    </p>
  );
}

function StuckCard({ incident }: { incident: StuckIncident }) {
  return (
    <article className="grid gap-2 rounded-card border border-border bg-surface p-4 shadow-card">
      <header className="flex flex-wrap items-center gap-2">
        <Link
          to={`/incidents/${encodeURIComponent(incident.id)}`}
          className="font-medium break-words text-accent hover:underline"
        >
          {incident.title}
        </Link>
        <IncidentStatusBadge status={incident.status} />
      </header>
      <p className="m-0 text-sm text-muted">
        {incident.target} · no change since <RelativeTime iso={incident.since} />
      </p>
      <JobLine incident={incident} />
      {incident.job_last_error !== null && (
        <code className="block rounded-control bg-surface-2 p-2 text-xs break-all whitespace-pre-wrap">
          {incident.job_last_error}
        </code>
      )}
    </article>
  );
}

export function StuckIncidents({ incidents }: { incidents: StuckIncident[] }) {
  if (incidents.length === 0) {
    return <p className="m-0 text-sm text-muted">None. No incident has stopped moving.</p>;
  }
  return (
    <ul className="m-0 grid list-none gap-3 p-0">
      {incidents.map((incident) => (
        <li key={incident.id}>
          <StuckCard incident={incident} />
        </li>
      ))}
    </ul>
  );
}
