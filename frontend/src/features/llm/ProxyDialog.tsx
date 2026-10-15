import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { resetLlmProxy, setLlmProxy } from "../../api/client";
import type { LlmConfig, LlmProvider } from "../../api/types";
import { Button } from "../../ui/Button";
import { Dialog } from "../../ui/Dialog";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";
import { INPUT_CLASS, LABEL_CLASS } from "../settings/formStyles";
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
    <form onSubmit={submit} className="grid gap-4">
      <p className="m-0 text-sm">
        Now: <span className="font-medium">{provider.proxy.display ?? "no proxy"}</span>
      </p>
      <label className={LABEL_CLASS}>
        New proxy URL
        <input
          name="llm-proxy-url"
          type="text"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="http://127.0.0.1:10950"
          maxLength={URL_MAX_LENGTH}
          value={url}
          onChange={(event) => setUrl(event.target.value)}
          className={INPUT_CLASS}
        />
      </label>
      {mutation.isError && (
        <p role="alert" className="m-0 text-sm text-critical">
          {settingsErrorText(mutation.error)}
        </p>
      )}
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate({ kind: "env" })}>
          Use the environment
        </Button>
        <Button variant="secondary" disabled={mutation.isPending} onClick={() => mutation.mutate({ kind: "none" })}>
          No proxy
        </Button>
        <Button type="submit" variant="primary" disabled={mutation.isPending || url.trim() === ""}>
          Save proxy
        </Button>
      </div>
    </form>
  );
}
