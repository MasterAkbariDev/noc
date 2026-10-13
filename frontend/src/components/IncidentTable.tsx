import { Link } from "react-router";
import type { IncidentSummary } from "../api/types";
import { formatConfidence, formatTime } from "./format";
import { StatusBadge } from "./StatusBadge";

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
];

const relativeFormat = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

function relativeTime(iso: string, nowMs: number): string {
  const then = Date.parse(iso);
  if (Number.isNaN(then)) {
    return iso;
  }
  const seconds = Math.round((then - nowMs) / 1000);
  for (const [unit, size] of RELATIVE_UNITS) {
    if (Math.abs(seconds) >= size) {
      return relativeFormat.format(Math.round(seconds / size), unit);
    }
  }
  return relativeFormat.format(seconds, "second");
}

function OpenedCell({ iso }: { iso: string }) {
  return (
    <time dateTime={iso} title={formatTime(iso)}>
      {relativeTime(iso, Date.now())}
    </time>
  );
}

function RootCauseCell({ incident }: { incident: IncidentSummary }) {
  return (
    <>
      {incident.root_cause_code ?? "-"}
      {incident.confidence !== null && <span className="muted"> {formatConfidence(incident.confidence)}</span>}
    </>
  );
}

export function IncidentTable({ incidents }: { incidents: IncidentSummary[] }) {
  if (incidents.length === 0) {
    return <p className="muted">No incidents match this filter.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Target</th>
            <th scope="col">Title</th>
            <th scope="col">Status</th>
            <th scope="col">Severity</th>
            <th scope="col">Root cause</th>
            <th scope="col">Opened</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr key={incident.id}>
              <td>{incident.target}</td>
              <td>
                <Link to={`/incidents/${incident.id}`}>{incident.title}</Link>
              </td>
              <td>
                <StatusBadge status={incident.status} />
              </td>
              <td>{incident.severity}</td>
              <td>
                <RootCauseCell incident={incident} />
              </td>
              <td>
                <OpenedCell iso={incident.opened_at} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
