import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { addLlmKey } from "../../api/client";
import type { LlmKeyTier, LlmProvider } from "../../api/types";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";
import { INPUT_CLASS, LABEL_CLASS } from "../settings/formStyles";
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
    <form onSubmit={submit} className="grid gap-4">
      <label className={LABEL_CLASS}>
        Provider
        <select value={provider} onChange={(event) => setProvider(event.target.value)} className={INPUT_CLASS}>
          {providers.map((item) => (
            <option key={item.name} value={item.name}>
              {item.name}
            </option>
          ))}
        </select>
      </label>
      <label className={LABEL_CLASS}>
        Billing tier
        <select value={tier} onChange={(event) => setTier(parseTier(event.target.value))} className={INPUT_CLASS}>
          {KEY_TIERS.map((item) => (
            <option key={item} value={item}>
              {tierLabel(item)}
            </option>
          ))}
        </select>
        <span className="text-xs font-normal text-muted">
          Paid keys get higher limits and are tried before free keys of the same provider.
        </span>
      </label>
      <label className={LABEL_CLASS}>
        Name
        <input
          name="llm-key-name"
          type="text"
          required
          maxLength={NAME_MAX_LENGTH}
          value={name}
          onChange={(event) => setName(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      <label className={LABEL_CLASS}>
        API key
        <input
          name="llm-key-secret"
          type="password"
          autoComplete="off"
          spellCheck={false}
          required
          maxLength={SECRET_MAX_LENGTH}
          value={secret}
          onChange={(event) => setSecret(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      {mutation.isError && (
        <p role="alert" className="m-0 text-sm text-critical">
          {settingsErrorText(mutation.error)}
        </p>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" onClick={onDone}>
          Cancel
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending}>
          Add key
        </Button>
      </div>
    </form>
  );
}
