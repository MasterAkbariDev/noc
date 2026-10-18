import { useQuery } from "@tanstack/react-query";
import { KeyRound, Plus } from "lucide-react";
import { useState } from "react";
import {
  finishSshKeyRotation,
  getFleet,
  offboardFleetHost,
  revokeSshKey,
  rotateSshKey,
  type Fleet,
  type FleetRow,
  type SshKey,
} from "../api/fleet";
import { useSession } from "../auth/session";
import { NodesWorkspace } from "../features/nodes/NodesWorkspace";
import { AddHostDialog, emptyDraft, type HostDraft } from "../features/fleet/AddHostDialog";
import { ConfirmCodeDialog, type CodeAction } from "../features/fleet/ConfirmCodeDialog";
import { GenerateKeyDialog } from "../features/fleet/GenerateKeyDialog";
import { KeysTable } from "../features/fleet/KeysTable";
import { ServersTable } from "../features/fleet/ServersTable";
import { SetupHostDialog } from "../features/fleet/SetupHostDialog";
import { FLEET_KEY, keysForHost } from "../features/fleet/view";
import { settingsErrorText } from "../features/settings/accountView";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { Alert, Button, Disclosure, ErrorState, PageHeader, Section, Skeleton } from "../ui";

const REFRESH_MS = 30_000;

export function FleetPage() {
  useDocumentTitle("Nodes");
  const { me } = useSession();
  return (
    <>
      <PageHeader
        title="Nodes"
        status="Every server the NOC looks after, reached by SSH or paired with another NOC. The panel only shows commands: you run them on the server yourself."
      />
      {me.role === "admin" ? (
        <NodesWorkspace ssh={<FleetContent />} />
      ) : (
        <Alert tone="info" title="Only admins manage the fleet">
          Ask an admin to add servers or keys.
        </Alert>
      )}
    </>
  );
}

function FleetContent() {
  const query = useQuery({ queryKey: [FLEET_KEY], queryFn: getFleet, refetchInterval: REFRESH_MS });
  if (query.isPending) {
    return <Skeleton lines={6} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="Could not load the fleet"
        message={settingsErrorText(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return <FleetSections fleet={query.data} />;
}

function rotateAction(key: SshKey): CodeAction {
  return {
    title: `Rotate ${key.label}?`,
    description:
      "The NOC makes a new key with the same limits. Run the commands it shows on each server, then press Finish rotation on the new key.",
    confirmLabel: "Make the new key",
    danger: false,
    doneText: "The new key is ready. Run these on each server, then finish the rotation.",
    run: async (code) => (await rotateSshKey(key.id, code)).steps,
  };
}

function finishAction(key: SshKey): CodeAction {
  return {
    title: `Finish rotation to ${key.label}?`,
    description: "Do this after the swap command ran on every server. The old key is retired and its private key deleted.",
    confirmLabel: "Finish rotation",
    danger: false,
    doneText: "Rotation finished. The old key is retired.",
    run: async (code) => {
      await finishSshKeyRotation(key.id, code);
      return [];
    },
  };
}

function revokeAction(key: SshKey): CodeAction {
  return {
    title: `Revoke ${key.label}?`,
    description: "The NOC deletes the private key at once, so the key cannot be used again. Remove its line from the servers too.",
    confirmLabel: "Revoke key",
    danger: true,
    doneText: "Revoked. Remove the key line on these servers:",
    run: async (code) => (await revokeSshKey(key.id, code)).steps,
  };
}

function offboardAction(row: FleetRow, hostId: string): CodeAction {
  return {
    title: `Offboard ${row.name}?`,
    description: "The server leaves the fleet list. Run the commands it shows to remove the helper and the NOC's keys from it.",
    confirmLabel: "Offboard server",
    danger: true,
    doneText: `${row.name} left the fleet. Clean the server up with:`,
    run: async (code) => (await offboardFleetHost(hostId, code)).steps,
  };
}

function FleetSections({ fleet }: { fleet: Fleet }) {
  const [hostDraft, setHostDraft] = useState<HostDraft | null>(null);
  const [generating, setGenerating] = useState(false);
  const [settingUp, setSettingUp] = useState<FleetRow | null>(null);
  const [action, setAction] = useState<CodeAction | null>(null);
  const activeKeys = fleet.keys.filter((key) => key.retired_at === null);
  const retiredKeys = fleet.keys.filter((key) => key.retired_at !== null);

  return (
    <>
      {!fleet.secrets_persistent && (
        <div className="mb-8">
          <Alert tone="warning" title="Keys would be lost on a container rebuild">
            The secrets folder is not on a mounted volume. Mount one at /var/lib/noc/secrets before you generate keys.
          </Alert>
        </div>
      )}
      <Section
        heading="Servers"
        description="Monitored targets and servers you added for SSH. Reachable and Helper come from the last Prometheus scrape."
        actions={
          <Button size="sm" variant="primary" onClick={() => setHostDraft(emptyDraft())}>
            <Plus aria-hidden="true" size={14} />
            Add a server
          </Button>
        }
      >
        {!fleet.metrics_available && (
          <Alert tone="unknown">Prometheus did not answer, so reachability and helper status are unknown.</Alert>
        )}
        <ServersTable
          rows={fleet.hosts}
          onSetUp={setSettingUp}
          onAddDetails={(row) => setHostDraft({ name: row.name, address: row.address, environment: row.environment })}
          onOffboard={(row) => row.host_id !== null && setAction(offboardAction(row, row.host_id))}
        />
      </Section>
      <Section
        heading="SSH keys"
        description="Ops keys for the ops user, short-lived bootstrap keys for new servers, and operator-shell keys for later."
        actions={
          <Button size="sm" variant="primary" onClick={() => setGenerating(true)}>
            <KeyRound aria-hidden="true" size={14} />
            Generate a key
          </Button>
        }
      >
        <KeysTable
          label="Key list"
          keys={activeKeys}
          allKeys={fleet.keys}
          empty="No keys yet. Generate one to set a server up."
          onRotate={(key) => setAction(rotateAction(key))}
          onFinish={(key) => setAction(finishAction(key))}
          onRevoke={(key) => setAction(revokeAction(key))}
        />
        {retiredKeys.length > 0 && (
          <Disclosure summary={`Retired keys (${retiredKeys.length})`} hint="Kept here for 30 days" quiet>
            <KeysTable label="Retired key list" keys={retiredKeys} allKeys={fleet.keys} empty="None." />
          </Disclosure>
        )}
      </Section>
      <AddHostDialog draft={hostDraft} onClose={() => setHostDraft(null)} />
      <GenerateKeyDialog
        open={generating}
        rules={fleet.rules}
        forcedCommands={fleet.forced_commands}
        onOpenChange={setGenerating}
      />
      <SetupHostDialog
        row={settingUp}
        keys={settingUp === null ? [] : keysForHost(fleet.keys, fleet.rules, settingUp)}
        onClose={() => setSettingUp(null)}
      />
      <ConfirmCodeDialog action={action} onClose={() => setAction(null)} />
    </>
  );
}
