import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent } from "react";
import { createJoinCode, joinPeer, refreshPeer, removePeer } from "../../api/client";
import type { PeerView } from "../../api/types";
import { useSession } from "../../auth/session";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { Field, Form, FormActions, FormMessage, TextArea, TextInput } from "../../ui/Form";
import { List, ListItem } from "../../ui/List";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";
import { PEERS_KEY, usePeersQuery } from "./queries";
import { directionLabel, peerStatusText } from "./view";

export function NodesAdmin() {
  const { me } = useSession();
  if (me.role !== "admin") {
    return null;
  }
  return <NodesSection />;
}

function NodesSection() {
  const query = usePeersQuery();
  return (
    <Section heading="Other NOC nodes">
      <p className="m-0 text-sm text-muted">
        Pair another NOC so this panel can show its servers, or let it show yours. Each code works once and expires after
        ten minutes. Keys stay on the node that owns them.
      </p>
      <div className="grid gap-3 md:grid-cols-2">
        <CreateCode />
        <JoinWithCode />
      </div>
      {query.isSuccess && query.data.length > 0 && (
        <List label="Paired nodes" gap="sm">
          {query.data.map((peer) => (
            <ListItem key={peer.id}>
              <PeerRow peer={peer} />
            </ListItem>
          ))}
        </List>
      )}
    </Section>
  );
}

function CreateCode() {
  const toast = useToast();
  const [name, setName] = useState("");
  const [code, setCode] = useState<string | null>(null);
  const mutation = useMutation({
    mutationFn: () => createJoinCode(name.trim()),
    onSuccess: (result) => {
      setCode(result.code);
      toast.success("Join code created. Paste it on the other node within ten minutes.");
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Card title="Let another node read this panel">
      <Form onSubmit={submit}>
        <Field label="Name for that node">
          <TextInput name="peer-name" maxLength={64} value={name} onChange={(event) => setName(event.target.value)} />
        </Field>
        <FormActions align="end">
          <Button type="submit" variant="primary" disabled={name.trim() === "" || mutation.isPending}>
            Create join code
          </Button>
        </FormActions>
      </Form>
      {code !== null && (
        <Field label="Join code (copy it to the other node)">
          <TextArea readOnly rows={3} value={code} onFocus={(event) => event.currentTarget.select()} />
        </Field>
      )}
    </Card>
  );
}

function JoinWithCode() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [code, setCode] = useState("");
  const mutation = useMutation({
    mutationFn: () => joinPeer(code.trim()),
    onSuccess: (peer) => {
      void queryClient.invalidateQueries({ queryKey: [PEERS_KEY] });
      setCode("");
      toast.success(`Joined ${peer.name}.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    mutation.mutate();
  }

  return (
    <Card title="Show another node's servers here">
      <Form onSubmit={submit}>
        <Field label="Join code from the other node">
          <TextArea rows={3} value={code} onChange={(event) => setCode(event.target.value)} spellCheck={false} />
        </Field>
        {mutation.isError && <FormMessage>{settingsErrorText(mutation.error)}</FormMessage>}
        <FormActions align="end">
          <Button type="submit" variant="primary" disabled={code.trim() === "" || mutation.isPending}>
            Join
          </Button>
        </FormActions>
      </Form>
    </Card>
  );
}

function PeerRow({ peer }: { peer: PeerView }) {
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
