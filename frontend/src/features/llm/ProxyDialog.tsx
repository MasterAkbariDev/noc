import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { resetLlmProxy, setLlmProxy } from "../../api/client";
import type { LlmConfig, LlmProvider } from "../../api/types";
import { Button, Dialog, Field, Form, FormActions, FormMessage, TextInput, useToast } from "../../ui";
import { settingsErrorText } from "../settings/accountView";
import { LLM_CONFIG_KEY } from "./queries";

const URL_MAX_LENGTH = 512;

type ProxyAction = { kind: "set"; url: string } | { kind: "none" } | { kind: "env" };

type ProxyDialogProps = {
  provider: LlmProvider | null;
  onClose: () => void;
};

export function ProxyDialog({ provider, onClose }: ProxyDialogProps) {
  return (
    <Dialog
      open={provider !== null}
      onOpenChange={(open) => {
        if (!open) {
          onClose();
        }
      }}
      title={provider === null ? "Proxy" : `Proxy for ${provider.name}`}
      description="Requests to this provider go through the proxy. Use http:// or https://; a user and password in the URL are stored with the keys and never shown."
    >
      {provider !== null && <ProxyForm provider={provider} onDone={onClose} />}
    </Dialog>
  );
}

function ProxyForm({ provider, onDone }: { provider: LlmProvider; onDone: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [url, setUrl] = useState("");

  const mutation = useMutation({
    mutationFn: (action: ProxyAction): Promise<LlmConfig> => {
      if (action.kind === "env") {
        return resetLlmProxy(provider.name);
      }
      return setLlmProxy(provider.name, action.kind === "set" ? action.url : null);
    },
    onSuccess: (config) => {
      queryClient.setQueryData([LLM_CONFIG_KEY], config);
      toast.success(`Saved the proxy for ${provider.name}.`);
      onDone();
    },
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate({ kind: "set", url: url.trim() });
  }

  return (
    <Form onSubmit={submit}>
      <p className="m-0 text-sm">
        Now: <span className="font-medium">{provider.proxy.display ?? "no proxy"}</span>
      </p>
      <Field label="New proxy URL">
        <TextInput
          name="llm-proxy-url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="http://127.0.0.1:10950"
          maxLength={URL_MAX_LENGTH}
          value={url}
          onChange={(event) => setUrl(event.target.value)}
        />
      </Field>
      {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
      <FormActions align="end">
        <Button variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate({ kind: "env" })}>
          Use the environment
        </Button>
        <Button variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate({ kind: "none" })}>
          No proxy
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending || url.trim() === ""}>
          Save proxy
        </Button>
      </FormActions>
    </Form>
  );
}
