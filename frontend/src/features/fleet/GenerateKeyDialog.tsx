import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { generateSshKey, type FleetEnvironment, type ForcedCommand, type SshKeyPurpose, type SshKeyRule } from "../../api/fleet";
import { Button, Checkbox, Dialog, Field, Form, FormActions, FormMessage, Select, TextInput, useToast } from "../../ui";
import { settingsErrorText } from "../settings/accountView";
import { CodeField } from "./FleetParts";
import {
  ENVIRONMENTS,
  FLEET_KEY,
  KEY_PURPOSES,
  environmentLabel,
  parseEnvironment,
  parsePurpose,
  purposeHint,
  purposeLabel,
  ruleFor,
} from "./view";

const NO_COMMAND = "";

type GenerateKeyDialogProps = {
  open: boolean;
  rules: SshKeyRule[];
  forcedCommands: ForcedCommand[];
  onOpenChange: (open: boolean) => void;
};

export function GenerateKeyDialog({ open, rules, forcedCommands, onOpenChange }: GenerateKeyDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Generate an SSH key"
      description="An ed25519 key pair is made on the NOC host. The private key and its passphrase stay in the NOC's secret store and are never shown."
    >
      {open && <GenerateKeyForm rules={rules} forcedCommands={forcedCommands} onDone={() => onOpenChange(false)} />}
    </Dialog>
  );
}

function GenerateKeyForm({
  rules,
  forcedCommands,
  onDone,
}: {
  rules: SshKeyRule[];
  forcedCommands: ForcedCommand[];
  onDone: () => void;
}) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [purpose, setPurpose] = useState<SshKeyPurpose>("ops");
  const [environment, setEnvironment] = useState<FleetEnvironment>("lab");
  const [pin, setPin] = useState("");
  const [days, setDays] = useState("");
  const [forcedCommand, setForcedCommand] = useState(NO_COMMAND);
  const [passphrase, setPassphrase] = useState(true);
  const [code, setCode] = useState("");
  const rule = ruleFor(rules, purpose);

  const mutation = useMutation({
    mutationFn: () =>
      generateSshKey({
        label: label.trim(),
        purpose,
        environment,
        from_pin: pin.trim() === "" ? null : pin.trim(),
        forced_command: rule?.allows_forced_command && forcedCommand !== NO_COMMAND ? forcedCommand : null,
        with_passphrase: passphrase,
        rotation_days: days.trim() === "" ? null : Number(days),
        totp: code.trim(),
      }),
    onSuccess: (key) => {
      void queryClient.invalidateQueries({ queryKey: [FLEET_KEY] });
      toast.success(`Generated ${key.label} (${key.fingerprint}).`);
      onDone();
    },
    onError: () => setCode(""),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  const lifetimeHint =
    rule === undefined
      ? undefined
      : `${rule.min_days}-${rule.max_days} days, ${rule.default_days} if left empty. The server refuses the key after that.`;

  return (
    <Form onSubmit={submit}>
      <Field label="Label">
        <TextInput name="key-label" required maxLength={64} value={label} onChange={(event) => setLabel(event.target.value)} />
      </Field>
      <Field label="Purpose" hint={purposeHint(purpose)}>
        <Select
          value={purpose}
          options={KEY_PURPOSES.map((item) => ({ value: item, label: purposeLabel(item) }))}
          onChange={(event) => setPurpose(parsePurpose(event.target.value))}
        />
      </Field>
      <Field label="Environment" hint="A production key can only go on production servers.">
        <Select
          value={environment}
          options={ENVIRONMENTS.map((item) => ({ value: item, label: environmentLabel(item) }))}
          onChange={(event) => setEnvironment(parseEnvironment(event.target.value))}
        />
      </Field>
      <Field
        label={rule?.needs_pin ? "NOC address (from=)" : "NOC address (from=, optional)"}
        hint="The server accepts the key only from these addresses. Separate several with commas."
      >
        <TextInput
          name="key-pin"
          required={rule?.needs_pin ?? false}
          maxLength={255}
          spellCheck={false}
          value={pin}
          onChange={(event) => setPin(event.target.value)}
        />
      </Field>
      <Field label="Lifetime in days" hint={lifetimeHint}>
        <TextInput name="key-days" inputMode="numeric" value={days} onChange={(event) => setDays(event.target.value)} />
      </Field>
      {rule?.allows_forced_command && (
        <Field label="Single purpose (command=)" hint="Only for a server where the key should do one fixed thing.">
          <Select
            value={forcedCommand}
            options={[
              { value: NO_COMMAND, label: "None" },
              ...forcedCommands.map((item) => ({ value: item.name, label: `${item.name}: ${item.command}` })),
            ]}
            onChange={(event) => setForcedCommand(event.target.value)}
          />
        </Field>
      )}
      <Checkbox
        label="Protect the private key with a passphrase"
        hint="The NOC makes one up and keeps it in the secret store."
        checked={passphrase}
        onChange={(event) => setPassphrase(event.target.checked)}
      />
      <CodeField value={code} onChange={setCode} />
      {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
      <FormActions align="end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          Generate key
        </Button>
      </FormActions>
    </Form>
  );
}
