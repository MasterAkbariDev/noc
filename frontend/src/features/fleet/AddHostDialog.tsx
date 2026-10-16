import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { addFleetHost, type FleetEnvironment } from "../../api/fleet";
import { Button, Dialog, Field, Form, FormActions, FormMessage, Select, TextInput, useToast } from "../../ui";
import { settingsErrorText } from "../settings/accountView";
import { CodeField } from "./FleetParts";
import { ENVIRONMENTS, FLEET_KEY, environmentLabel, parseEnvironment } from "./view";

export type HostDraft = { name: string; address: string; environment: FleetEnvironment };

const EMPTY_DRAFT: HostDraft = { name: "", address: "", environment: "lab" };
const DEFAULT_PORT = 22;
const DEFAULT_USER = "ops";

type AddHostDialogProps = { draft: HostDraft | null; onClose: () => void };

export function AddHostDialog({ draft, onClose }: AddHostDialogProps) {
  return (
    <Dialog
      open={draft !== null}
      onOpenChange={(open) => !open && onClose()}
      title="Add a server"
      description="Only the address and login details are stored. The NOC does not connect to the server."
    >
      {draft !== null && <AddHostForm draft={draft} onDone={onClose} />}
    </Dialog>
  );
}

export function emptyDraft(): HostDraft {
  return { ...EMPTY_DRAFT };
}

function AddHostForm({ draft, onDone }: { draft: HostDraft; onDone: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState(draft.name);
  const [address, setAddress] = useState(draft.address);
  const [port, setPort] = useState(String(DEFAULT_PORT));
  const [user, setUser] = useState(DEFAULT_USER);
  const [environment, setEnvironment] = useState<FleetEnvironment>(draft.environment);
  const [code, setCode] = useState("");

  const mutation = useMutation({
    mutationFn: () =>
      addFleetHost({
        name: name.trim(),
        address: address.trim(),
        ssh_port: Number(port),
        ssh_user: user.trim(),
        environment,
        totp: code.trim(),
      }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [FLEET_KEY] });
      toast.success(`Added ${name.trim()}. Open Set up to get its command.`);
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
      <Field label="Name" hint="The same name the NOC uses for it, e.g. demo-2.">
        <TextInput name="host-name" required maxLength={63} value={name} onChange={(event) => setName(event.target.value)} />
      </Field>
      <Field label="IP address">
        <TextInput
          name="host-address"
          required
          maxLength={64}
          spellCheck={false}
          value={address}
          onChange={(event) => setAddress(event.target.value)}
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="SSH port">
          <TextInput
            name="host-port"
            inputMode="numeric"
            required
            value={port}
            onChange={(event) => setPort(event.target.value)}
          />
        </Field>
        <Field label="SSH user" hint="Never root.">
          <TextInput name="host-user" required maxLength={32} value={user} onChange={(event) => setUser(event.target.value)} />
        </Field>
      </div>
      <Field label="Environment" hint="Production and lab keys are kept apart.">
        <Select
          value={environment}
          options={ENVIRONMENTS.map((item) => ({ value: item, label: environmentLabel(item) }))}
          onChange={(event) => setEnvironment(parseEnvironment(event.target.value))}
        />
      </Field>
      <CodeField value={code} onChange={setCode} />
      {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
      <FormActions align="end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          Add server
        </Button>
      </FormActions>
    </Form>
  );
}
