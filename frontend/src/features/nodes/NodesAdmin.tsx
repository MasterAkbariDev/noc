import {useMutation, useQueryClient} from "@tanstack/react-query";
import {useState, type FormEvent} from "react";
import {createJoinCode, joinPeer, refreshPeer, removePeer} from "../../api/client";
import type {PeerView} from "../../api/types";
import {Button} from "../../ui/Button";
import {Card} from "../../ui/Card";
import {Field, Form, FormActions, FormMessage, TextArea, TextInput} from "../../ui/Form";
import {RelativeTime} from "../../ui/RelativeTime";
import {useToast} from "../../ui/Toaster";
import {settingsErrorText} from "../settings/accountView";
import {PEERS_KEY} from "./queries";
import {directionLabel, peerStatusText} from "./view";

export function AddNode() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [token, setToken] = useState("");
  const mutation = useMutation({
    mutationFn: () => joinPeer(token.trim(), label.trim()),
    onSuccess: (peer) => {
      void queryClient.invalidateQueries({ queryKey: [PEERS_KEY] });
      setLabel("");
      setToken("");
      toast.success(`Added ${peer.name}.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Card title="Add a NOC node">
      <Form onSubmit={submit}>
        <Field label="Label">
          <TextInput maxLength={64} value={label} onChange={(event) => setLabel(event.target.value)} />
        </Field>
        <Field label="Auth token">
          <TextArea rows={2} spellCheck={false} value={token} onChange={(event) => setToken(event.target.value)} />
        </Field>
        {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
        <FormActions align="end">
          <Button
            type="submit"
            variant="primary"
            disabled={label.trim() === "" || token.trim() === "" || mutation.isPending}
          >
            Add node
          </Button>
        </FormActions>
      </Form>
    </Card>
  );
}

export function CreateToken() {
  const toast = useToast();
  const [label, setLabel] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => createJoinCode(label.trim()),
    onSuccess: (result) => {
      setToken(result.code);
      toast.success("Auth token created. Give it to the other NOC within ten minutes.");
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Card title="Give an auth token to another NOC">
      <Form onSubmit={submit}>
        <Field label="Name for that NOC">
          <TextInput maxLength={64} value={label} onChange={(event) => setLabel(event.target.value)} />
        </Field>
        <FormActions align="end">
          <Button type="submit" disabled={label.trim() === "" || mutation.isPending}>
            Create auth token
          </Button>
        </FormActions>
      </Form>
      {token !== null && (
        <Field label="Auth token">
          <TextArea readOnly rows={3} value={token} onFocus={(event) => event.currentTarget.select()} />
        </Field>
      )}
    </Card>
  );
}

export function PeerRow({ peer }: { peer: PeerView }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const refresh = useMutation({
    mutationFn: () => refreshPeer(peer.id),
    onSuccess: () => void queryClient.invalidateQueries({ queryKey: [PEERS_KEY] }),
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const remove = useMutation({
    mutationFn: () => removePeer(peer.id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [PEERS_KEY] });
      toast.success(`Removed ${peer.name}.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  return (
    <div className="flex flex-wrap items-center justify-between gap-3">
      <div className="grid gap-0.5">
        <span className="font-medium break-all">{peer.name}</span>
        <span className="text-xs text-muted">{directionLabel(peer)}</span>
        <span className="text-xs">{peerStatusText(peer, Date.now())}</span>
        {peer.last_seen_at && (
          <span className="text-xs text-muted">
            Read <RelativeTime iso={peer.last_seen_at} />
          </span>
        )}
      </div>
      <div className="flex gap-2">
        {peer.direction === "follows" && peer.status === "paired" && (
          <Button size="sm" aria-label={`Refresh ${peer.name}`} disabled={refresh.isPending} onClick={() => refresh.mutate()}>
            Refresh
          </Button>
        )}
        <Button size="sm" variant="danger" aria-label={`Remove ${peer.name}`} disabled={remove.isPending} onClick={() => remove.mutate()}>
          Remove
        </Button>
      </div>
    </div>
  );
}
