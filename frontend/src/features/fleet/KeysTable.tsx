import type { SshKey } from "../../api/fleet";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { DataTable, type Column } from "../../ui/DataTable";
import { RelativeTime } from "../../ui/RelativeTime";
import { dayDistance, environmentLabel, finishesRotation, purposeLabel, shortFingerprint, stateView, waitingRotation } from "./view";

type KeysTableProps = {
  label: string;
  keys: SshKey[];
  allKeys: SshKey[];
  empty: string;
  onRotate?: (key: SshKey) => void;
  onFinish?: (key: SshKey) => void;
  onRevoke?: (key: SshKey) => void;
};

function rotationNote(allKeys: SshKey[], sshKey: SshKey): string | null {
  if (finishesRotation(allKeys, sshKey)) {
    return "New key: run the swap, then finish the rotation";
  }
  if (waitingRotation(allKeys, sshKey) !== undefined) {
    return "Old key: still in use until the rotation is finished";
  }
  return null;
}

function KeyCell({ sshKey, allKeys }: { sshKey: SshKey; allKeys: SshKey[] }) {
  const note = rotationNote(allKeys, sshKey);
  return (
    <div className="grid gap-0.5">
      <span className="font-medium break-all">{sshKey.label}</span>
      {note !== null && <span className="text-xs text-info">{note}</span>}
      <span className="font-mono text-xs text-muted" title={sshKey.fingerprint}>
        {shortFingerprint(sshKey.fingerprint)}
      </span>
      <span className="text-xs text-muted">
        by {sshKey.created_by}, <RelativeTime iso={sshKey.created_at} />
      </span>
    </div>
  );
}

function RulesCell({ sshKey }: { sshKey: SshKey }) {
  const parts = [
    sshKey.from_pin === null ? "from anywhere" : `from ${sshKey.from_pin}`,
    sshKey.forced_command === null ? null : `only ${sshKey.forced_command}`,
    sshKey.has_passphrase ? "passphrase" : "no passphrase",
  ].filter((part) => part !== null);
  return <span className="text-sm break-words">{parts.join(" · ")}</span>;
}

export function KeysTable({ label, keys, allKeys, empty, onRotate, onFinish, onRevoke }: KeysTableProps) {
  const columns: Column<SshKey>[] = [
    { key: "key", header: "Key", cell: (key) => <KeyCell sshKey={key} allKeys={allKeys} /> },
    {
      key: "purpose",
      header: "Purpose",
      cell: (key) => (
        <div className="grid gap-1 text-sm">
          <span>{purposeLabel(key.purpose)}</span>
          <span className="text-xs text-muted">{environmentLabel(key.environment)}</span>
        </div>
      ),
    },
    { key: "rules", header: "Limits", cell: (key) => <RulesCell sshKey={key} /> },
    {
      key: "life",
      header: "Lifetime",
      cell: (key) => {
        const state = stateView(key.state);
        return (
          <div className="grid justify-items-start gap-1 text-sm">
            <Badge tone={state.tone}>{state.label}</Badge>
            <span className="text-xs text-muted">
              {key.retired_at === null ? `expires ${dayDistance(key.expires_at)}` : `retired ${dayDistance(key.retired_at)}`}
            </span>
          </div>
        );
      },
    },
    {
      key: "hosts",
      header: "Installed on",
      cell: (key) => <span className="text-sm">{key.hosts.length === 0 ? "—" : key.hosts.join(", ")}</span>,
    },
  ];
  if (onRotate !== undefined && onFinish !== undefined && onRevoke !== undefined) {
    columns.push({
      key: "actions",
      header: "Actions",
      cell: (key) => (
        <div className="flex flex-wrap gap-2">
          {finishesRotation(allKeys, key) && (
            <Button size="sm" variant="primary" aria-label={`Finish rotation to ${key.label}`} onClick={() => onFinish(key)}>
              Finish rotation
            </Button>
          )}
          {waitingRotation(allKeys, key) === undefined && !finishesRotation(allKeys, key) && (
            <Button size="sm" aria-label={`Rotate ${key.label}`} onClick={() => onRotate(key)}>
              Rotate
            </Button>
          )}
          <Button size="sm" variant="danger" aria-label={`Revoke ${key.label}`} onClick={() => onRevoke(key)}>
            Revoke
          </Button>
        </div>
      ),
    });
  }

  return <DataTable label={label} columns={columns} rows={keys} rowKey={(key) => key.id} minWidth="lg" empty={empty} />;
}
