import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { addEndpoint, checkEndpoint, getEndpoints, removeEndpoint } from "../../api/client";
import type { EndpointView } from "../../api/types";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { Field, Form, FormActions, FormMessage, TextInput } from "../../ui/Form";
import { List, ListItem } from "../../ui/List";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";

const ENDPOINTS_KEY = "endpoints";

export function EndpointsSection() {
  const query = useQuery({ queryKey: [ENDPOINTS_KEY], queryFn: getEndpoints });
  return (
    <Section heading="Servers without NOC">
      <p className="m-0 text-sm text-muted">
        Servers that run no NOC. The panel checks them over the network: whether the SSH port answers, and whether the
        web address responds. Nothing is installed on them.
      </p>
      <AddEndpoint />
      {query.isSuccess && query.data.length > 0 && (
        <List label="Servers without NOC" gap="sm">
          {query.data.map((endpoint) => (
            <ListItem key={endpoint.id}>
              <EndpointRow endpoint={endpoint} />
            </ListItem>
          ))}
        </List>
      )}
    </Section>
  );
}

function AddEndpoint() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [name, setName] = useState("");
  const [host, setHost] = useState("");
  const [port, setPort] = useState("22");
  const [url, setUrl] = useState("");
  const mutation = useMutation({
    mutationFn: () =>
      addEndpoint({
        name: name.trim(),
        host: host.trim(),
        ssh_port: Number(port) || 22,
        url: url.trim() === "" ? null : url.trim(),
      }),
    onSuccess: (endpoint) => {
      void queryClient.invalidateQueries({ queryKey: [ENDPOINTS_KEY] });
      setName("");
      setHost("");
      setPort("22");
      setUrl("");
      toast.success(`Added ${endpoint.name}. Check it to see its status.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Card title="Add a server without NOC">
      <Form onSubmit={submit}>
        <Field label="Label">
          <TextInput maxLength={64} value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <Field label="Address (host name or IP)">
          <TextInput value={host} onChange={(event) => setHost(event.target.value)} spellCheck={false} />
        </Field>
        <Field label="SSH port">
          <TextInput inputMode="numeric" value={port} onChange={(event) => setPort(event.target.value)} />
        </Field>
        <Field label="Web address (optional)">
          <TextInput placeholder="https://example.com" value={url} onChange={(event) => setUrl(event.target.value)} />
        </Field>
        {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
        <FormActions align="end">
          <Button type="submit" variant="primary" disabled={name.trim() === "" || host.trim() === "" || mutation.isPending}>
            Add server
          </Button>
        </FormActions>
      </Form>
    </Card>
  );
}

function EndpointRow({ endpoint }: { endpoint: EndpointView }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const check = useMutation({
    mutationFn: () => checkEndpoint(endpoint.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: [ENDPOINTS_KEY] }),
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const remove = useMutation({
    mutationFn: () => removeEndpoint(endpoint.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [ENDPOINTS_KEY] });
      toast.success(`Removed ${endpoint.name}.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const result = endpoint.last_result;

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="grid gap-0.5">
        <span className="font-medium break-all">{endpoint.name}</span>
        <span className="text-xs text-muted break-all">
          {endpoint.host}:{endpoint.ssh_port}
          {endpoint.url ? ` · ${endpoint.url}` : ""}
        </span>
        {result === null ? (
          <span className="text-xs text-muted">Not checked yet</span>
        ) : (
          <span className="text-xs">
            SSH {result.ssh.open ? `answers${result.ssh.banner ? ` (${result.ssh.banner})` : ""}` : "does not answer"}
            {result.web ? ` · web ${result.web.ok ? `HTTP ${result.web.status}` : "not responding"}` : ""}
          </span>
        )}
        {endpoint.last_checked_at && (
          <span className="text-xs text-muted">
            Checked <RelativeTime iso={endpoint.last_checked_at} />
          </span>
        )}
      </div>
      <div className="flex gap-2">
        <Button size="sm" aria-label={`Check ${endpoint.name}`} disabled={check.isPending} onClick={() => check.mutate()}>
          Check now
        </Button>
        <Button size="sm" variant="danger" aria-label={`Remove ${endpoint.name}`} disabled={remove.isPending} onClick={() => remove.mutate()}>
          Remove
        </Button>
      </div>
    </div>
  );
}
