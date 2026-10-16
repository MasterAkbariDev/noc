import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { getPasteCommand, markKeyInstalled, type FleetRow, type SshKey } from "../../api/fleet";
import { Alert, Button, Checkbox, Dialog, Field, Form, FormActions, FormMessage, Select, Skeleton, useToast } from "../../ui";
import { settingsErrorText } from "../settings/accountView";
import { CodeField, StepsList } from "./FleetParts";
import { FLEET_KEY, environmentLabel, purposeLabel, shortFingerprint } from "./view";

type SetupHostDialogProps = { row: FleetRow | null; keys: SshKey[]; onClose: () => void };

export function SetupHostDialog({ row, keys, onClose }: SetupHostDialogProps) {
  return (
    <Dialog
      open={row !== null}
      onOpenChange={(open) => !open && onClose()}
      title={row === null ? "Set up a server" : `Set up ${row.name}`}
      description="Copy the commands and run them yourself. The panel never sends anything to a server."
    >
      {row !== null && row.host_id !== null && <SetupBody hostId={row.host_id} row={row} keys={keys} onDone={onClose} />}
    </Dialog>
  );
}

function SetupBody({ hostId, row, keys, onDone }: { hostId: string; row: FleetRow; keys: SshKey[]; onDone: () => void }) {
  const [keyId, setKeyId] = useState(keys[0]?.id ?? "");

  if (keys.length === 0) {
    return (
      <Alert tone="info" title="No key to install yet">
        Generate an ops or bootstrap key for {environmentLabel(row.environment).toLowerCase()} servers first.
      </Alert>
    );
  }

  return (
    <div className="grid gap-4">
      <Field label="Key to install">
        <Select
          value={keyId}
          options={keys.map((key) => ({ value: key.id, label: `${key.label} (${purposeLabel(key.purpose)}, ${shortFingerprint(key.fingerprint)})` }))}
          onChange={(event) => setKeyId(event.target.value)}
        />
      </Field>
      <PasteSteps hostId={hostId} keyId={keyId} />
      <MarkInstalledForm hostId={hostId} keyId={keyId} onDone={onDone} />
    </div>
  );
}

function PasteSteps({ hostId, keyId }: { hostId: string; keyId: string }) {
  const query = useQuery({
    queryKey: [FLEET_KEY, "paste", hostId, keyId],
    queryFn: () => getPasteCommand(hostId, keyId),
  });
  if (query.isPending) {
    return <Skeleton lines={3} />;
  }
  if (query.isError) {
    return <FormMessage>{settingsErrorText(query.error)}</FormMessage>;
  }
  return <StepsList steps={query.data.steps} />;
}

function MarkInstalledForm({ hostId, keyId, onDone }: { hostId: string; keyId: string; onDone: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [sudoOk, setSudoOk] = useState(false);
  const [code, setCode] = useState("");
  const mutation = useMutation({
    mutationFn: () => markKeyInstalled(hostId, keyId, sudoOk, code.trim()),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [FLEET_KEY] });
      toast.success("Marked the key as installed.");
      onDone();
    },
    onError: () => setCode(""),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Form onSubmit={submit}>
      <p className="m-0 text-sm">After the first command has run, tell the NOC what it printed.</p>
      <Checkbox
        label='It printed "sudo scope OK"'
        hint="Leave this off if it printed a warning: the ops user must not have sudo rights."
        checked={sudoOk}
        onChange={(event) => setSudoOk(event.target.checked)}
      />
      <CodeField value={code} onChange={setCode} />
      {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
      <FormActions align="end">
        <Button variant="secondary" onClick={onDone}>
          Close
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending || keyId === ""}>
          Mark as installed
        </Button>
      </FormActions>
    </Form>
  );
}
