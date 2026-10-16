import type { IncidentSummary } from "../../api/types";
import { percentFromFraction } from "../../lib/format";
import { DataTable, IncidentStatusBadge, RelativeTime, SeverityBadge, Term, type Column } from "../../ui";
import { rootCauseLabel } from "./filters";
import { IncidentLink } from "../incident/IncidentLink";

const COLUMNS: Column<IncidentSummary>[] = [
  {
    key: "severity",
    header: "Severity",
    cell: (incident) => <SeverityBadge severity={incident.severity} />,
    className: "whitespace-nowrap",
  },
  {
    key: "title",
    header: "Title",
    cell: (incident) => (
      <IncidentLink id={incident.id} className="font-medium text-accent hover:underline">
        {incident.title}
      </IncidentLink>
    ),
    className: "break-words font-semibold sm:min-w-[14rem]",
    labelOnPhone: false,
  },
  {
    key: "target",
    header: "Server",
    cell: (incident) => <span className="whitespace-nowrap">{incident.target}</span>,
    className: "whitespace-nowrap",
  },
  {
    key: "status",
    header: "Status",
    cell: (incident) => <IncidentStatusBadge status={incident.status} />,
    className: "whitespace-nowrap",
  },
  {
    key: "root-cause",
    header: "Likely cause",
    cell: (incident) => <RootCause incident={incident} />,
    className: "sm:min-w-[10rem]",
  },
  {
    key: "opened",
    header: "Opened",
    cell: (incident) => <RelativeTime iso={incident.opened_at} className="whitespace-nowrap" />,
    className: "whitespace-nowrap",
  },
];

function RootCause({ incident }: { incident: IncidentSummary }) {
  if (incident.root_cause_code === null) {
    return <span className="text-muted">Not diagnosed yet</span>;
  }
  return (
    <span>
      <Term technical={incident.root_cause_code}>{rootCauseLabel(incident.root_cause_code)}</Term>
      {incident.confidence !== null && (
        <span className="text-muted">, {percentFromFraction(incident.confidence)} sure</span>
      )}
    </span>
  );
}

type IncidentRowsProps = {
  incidents: IncidentSummary[];
  emptyText: string;
};

export function IncidentRows({ incidents, emptyText }: IncidentRowsProps) {
  return (
    <DataTable
      label="Incidents"
      columns={COLUMNS}
      rows={incidents}
      rowKey={(incident) => incident.id}
      empty={emptyText}
    />
  );
}
