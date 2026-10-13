import { Link } from "react-router";
import type { IncidentSummary } from "../api/types";
import { formatConfidence, formatTime } from "./format";
import { StatusBadge } from "./StatusBadge";

export function IncidentTable({ incidents }: { incidents: IncidentSummary[] }) {
  if (incidents.length === 0) {
    return <p className="muted">No incidents match this filter.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Title</th>
            <th scope="col">Status</th>
            <th scope="col">Severity</th>
            <th scope="col">Opened</th>
            <th scope="col">Root cause</th>
            <th scope="col">Confidence</th>
          </tr>
        </thead>
        <tbody>
          {incidents.map((incident) => (
            <tr key={incident.id}>
              <td>
                <Link to={`/incidents/${incident.id}`}>{incident.title}</Link>
              </td>
              <td>
                <StatusBadge status={incident.status} />
              </td>
              <td>{incident.severity}</td>
              <td>{formatTime(incident.opened_at)}</td>
              <td>{incident.root_cause_code ?? "-"}</td>
              <td>{formatConfidence(incident.confidence)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
