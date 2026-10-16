import type { FleetRow } from "../../api/fleet";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { DataTable, type Column } from "../../ui/DataTable";
import { List, ListItem } from "../../ui/List";
import { StatusDot } from "../../ui/StatusDot";
import { dayDistance, environmentLabel, helperView, purposeLabel, sshLine, stateView, sudoView, yesNoView } from "./view";

type ServersTableProps = {
  rows: FleetRow[];
  onSetUp: (row: FleetRow) => void;
  onAddDetails: (row: FleetRow) => void;
  onOffboard: (row: FleetRow) => void;
};

function Status({ view }: { view: { label: string; tone: Parameters<typeof StatusDot>[0]["tone"] } }) {
  return <StatusDot tone={view.tone} label={view.label} showLabel />;
}

function ServerCell({ row }: { row: FleetRow }) {
  const ssh = sshLine(row);
  return (
    <div className="grid gap-0.5">
      <span className="flex flex-wrap items-center gap-2 font-medium">
        {row.name}
        <Badge tone={row.environment === "prod" ? "warning" : "neutral"}>{environmentLabel(row.environment)}</Badge>
      </span>
      <span className="text-xs text-muted break-all">{ssh ?? row.address}</span>
      {row.notes.map((note) => (
        <span key={note} className="text-xs text-warning">
          {note}
        </span>
      ))}
    </div>
  );
}

function KeysCell({ row }: { row: FleetRow }) {
  if (row.keys.length === 0) {
    return <span className="text-sm text-muted">{row.host_id === null ? "—" : "No key yet"}</span>;
  }
  return (
    <List gap="xs">
      {row.keys.map((key) => {
        const state = stateView(key.state);
        return (
          <ListItem key={key.key_id}>
            <span className="grid gap-0.5 text-sm">
              <span className="flex flex-wrap items-center gap-2">
                {key.label}
                <Badge tone={state.tone}>{state.label}</Badge>
              </span>
              <span className="text-xs text-muted">
                {purposeLabel(key.purpose)} · installed {dayDistance(key.installed_at)} · rotate {dayDistance(key.rotation_due_at)}
              </span>
            </span>
          </ListItem>
        );
      })}
    </List>
  );
}

export function ServersTable({ rows, onSetUp, onAddDetails, onOffboard }: ServersTableProps) {
  const columns: Column<FleetRow>[] = [
    { key: "server", header: "Server", cell: (row) => <ServerCell row={row} /> },
    {
      key: "reachable",
      header: "Reachable",
      cell: (row) => <Status view={row.target_id === null ? { label: "Not monitored", tone: "neutral" } : yesNoView(row.reachable, "Yes", "No")} />,
    },
    { key: "helper", header: "Helper", cell: (row) => <Status view={helperView(row)} /> },
    { key: "keys", header: "Keys", cell: (row) => <KeysCell row={row} /> },
    { key: "sudo", header: "Sudo scope", cell: (row) => <Status view={sudoView(row)} /> },
    {
      key: "automation",
      header: "Automation",
      cell: (row) => <span className="text-sm">{row.automation_label ?? "—"}</span>,
    },
    {
      key: "actions",
      header: "Actions",
      cell: (row) =>
        row.host_id === null ? (
          <Button size="sm" aria-label={`Add SSH details for ${row.name}`} onClick={() => onAddDetails(row)}>
            Add SSH details
          </Button>
        ) : (
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="primary" aria-label={`Set up ${row.name}`} onClick={() => onSetUp(row)}>
              Set up
            </Button>
            <Button size="sm" variant="danger" aria-label={`Offboard ${row.name}`} onClick={() => onOffboard(row)}>
              Offboard
            </Button>
          </div>
        ),
    },
  ];

  return (
    <DataTable
      label="Server status"
      columns={columns}
      rows={rows}
      rowKey={(row) => row.name}
      minWidth="lg"
      empty="No servers yet. Add one, or register a target with noc targets add."
    />
  );
}
