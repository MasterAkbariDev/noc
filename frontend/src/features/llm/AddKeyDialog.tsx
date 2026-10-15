import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { addLlmKey } from "../../api/client";
import type { LlmKeyTier, LlmProvider } from "../../api/types";
import { Button, Dialog, Field, Form, FormActions, FormMessage, Select, TextInput, useToast } from "../../ui";
import { settingsErrorText } from "../settings/accountView";
import { LLM_CONFIG_KEY } from "./queries";
import { KEY_TIERS, parseTier, tierLabel } from "./view";

const NAME_MAX_LENGTH = 64;
const SECRET_MAX_LENGTH = 256;

type AddKeyDialogProps = {
  open: boolean;
  providers: LlmProvider[];
  onOpenChange: (open: boolean) => void;
};

export function AddKeyDialog({ open, providers, onOpenChange }: AddKeyDialogProps) {
  return (
    <Dialog
      open={open}
      onOpenChange={onOpenChange}
      title="Add an API key"
      description="The key is stored in a file on the NOC host, never in the database, and is never shown again."
    >
      {open && <AddKeyForm providers={providers} onDone={() => onOpenChange(false)} />}
    </Dialog>
  );
}

function AddKeyForm({ providers, onDone }: { providers: LlmProvider[]; onDone: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [provider, setProvider] = useState(providers[0]?.name ?? "");
  const [tier, setTier] = useState<LlmKeyTier>("free");
  const [name, setName] = useState("");
  const [secret, setSecret] = useState("");

  const mutation = useMutation({
    mutationFn: () => addLlmKey({ provider, tier, name: name.trim(), secret: secret.trim() }),
    onSuccess: (key) => {
      setSecret("");
      void queryClient.invalidateQueries({ queryKey: [LLM_CONFIG_KEY] });
      toast.success(`Added ${key.name ?? key.provider} (…${key.last4}). Agents use it within a minute.`);
      onDone();
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Form onSubmit={submit}>
      <Field label="Provider">
        <Select
          value={provider}
          options={providers.map((item) => ({ value: item.name, label: item.name }))}
          onChange={(event) => setProvider(event.target.value)}
        />
      </Field>
      <Field label="Billing tier" hint="Paid keys get higher limits and are tried before free keys of the same provider.">
        <Select
          value={tier}
          options={KEY_TIERS.map((item) => ({ value: item, label: tierLabel(item) }))}
          onChange={(event) => setTier(parseTier(event.target.value))}
        />
      </Field>
      <Field label="Name">
        <TextInput
          name="llm-key-name"
          required
          maxLength={NAME_MAX_LENGTH}
          value={name}
          onChange={(event) => setName(event.target.value)}
        />
      </Field>
      <Field label="API key">
        <TextInput
          name="llm-key-secret"
          type="password"
          autoComplete="off"
          spellCheck={false}
          required
          maxLength={SECRET_MAX_LENGTH}
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
        />
      </Field>
      {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
      <FormActions align="end">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          Add key
        </Button>
      </FormActions>
    </Form>
  );
}
