import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { KeyRound, Plus, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { checkLlmKey, checkLlmProxy, getLlmConfig, revokeLlmKey } from "../../api/client";
import type { LlmCheck, LlmManagedKey, LlmModelLimit, LlmProvider } from "../../api/types";
import { useSession } from "../../auth/session";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { DataTable, type Column } from "../../ui/DataTable";
import { Dialog } from "../../ui/Dialog";
import { ErrorState } from "../../ui/ErrorState";
import { DescriptionList } from "../../ui/List";
import { RelativeTime } from "../../ui/RelativeTime";
import { Section } from "../../ui/Section";
import { Skeleton } from "../../ui/Skeleton";
import { useToast } from "../../ui/Toaster";
import { settingsErrorText } from "../settings/accountView";
import { AddKeyDialog } from "./AddKeyDialog";
import { ProxyDialog } from "./ProxyDialog";
import { LLM_CONFIG_KEY } from "./queries";
import { checkSummary, keySourceLabel, keyTitle, maskedKey, proxySourceLabel, tierLabel, tierTone } from "./view";

type CheckState = { status: "pending" } | { status: "done"; check: LlmCheck } | { status: "error"; message: string };

export function LlmAdmin() {
  const { me } = useSession();
  if (me.role !== "admin") {
    return null;
  }
  return <LlmSection />;
}

function LlmSection() {
  const query = useQuery({ queryKey: [LLM_CONFIG_KEY], queryFn: getLlmConfig });
  const [adding, setAdding] = useState(false);
  const [proxyFor, setProxyFor] = useState<LlmProvider | null>(null);
  const [revoking, setRevoking] = useState<LlmManagedKey | null>(null);

  return (
    <Section heading="Language models">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-sm text-muted">
          API keys and proxies for the model providers. Changes reach the agents within a minute, without a restart.
        </p>
        <Button size="sm" variant="primary" disabled={!query.isSuccess} onClick={() => setAdding(true)}>
          <Plus aria-hidden="true" size={14} />
          Add API key
        </Button>
      </div>
      {query.isPending && <Skeleton lines={4} />}
      {query.isError && (
        <ErrorState
          title="Could not load the model settings"
          message={settingsErrorText(query.error)}
          onRetry={() => void query.refetch()}
        />
      )}
      {query.isSuccess && (
        <>
          {!query.data.secrets_persistent && (
            <p role="status" className="m-0 flex items-start gap-2 rounded-control bg-warning-soft px-3 py-2 text-sm">
              <TriangleAlert aria-hidden="true" size={16} className="mt-0.5 shrink-0 text-warning" />
              The secrets folder is not on a mounted volume, so keys added here are lost when the NOC container is
              recreated. Mount a volume at /var/lib/noc/secrets (the compose files in the repository do).
            </p>
          )}
          {query.data.mode !== "live" && (
            <p className="m-0 text-sm text-muted">
              The NOC runs in {query.data.mode} mode, so agents read recorded answers and do not use these keys.
            </p>
          )}
          <div className="grid gap-3 md:grid-cols-2">
            {query.data.providers.map((provider) => (
              <ProviderCard key={provider.name} provider={provider} onEditProxy={() => setProxyFor(provider)} />
            ))}
          </div>
          <KeysTable keys={query.data.keys} onRevoke={setRevoking} />
          <AddKeyDialog open={adding} providers={query.data.providers} onOpenChange={setAdding} />
          <ProxyDialog provider={proxyFor} onClose={() => setProxyFor(null)} />
          <RevokeKeyDialog llmKey={revoking} onClose={() => setRevoking(null)} />
        </>
      )}
    </Section>
  );
}

function ProviderCard({ provider, onEditProxy }: { provider: LlmProvider; onEditProxy: () => void }) {
  const [check, setCheck] = useState<CheckState | null>(null);
  const mutation = useMutation({
    mutationFn: () => checkLlmProxy(provider.name),
    onMutate: () => setCheck({ status: "pending" }),
    onSuccess: (result) => setCheck({ status: "done", check: result }),
    onError: (error) => setCheck({ status: "error", message: settingsErrorText(error) }),
  });

  return (
    <Card title={provider.name}>
      <DescriptionList
        items={[
          { key: "endpoint", term: "Endpoint", detail: <span className="break-all">{provider.base_url}</span> },
          {
            key: "proxy",
            term: "Proxy",
            detail: (
              <span className="break-all">
                {provider.proxy.display ?? "none"}{" "}
                <span className="text-xs text-muted">({proxySourceLabel(provider.proxy.source)})</span>
              </span>
            ),
          },
        ]}
      />
      <div className="mt-3 flex flex-wrap gap-2">
        <Button size="sm" onClick={onEditProxy}>
          Change proxy
        </Button>
        <Button
          size="sm"
          disabled={provider.proxy.display === null || mutation.isPending}
          onClick={() => mutation.mutate()}
        >
          Check proxy
        </Button>
      </div>
      <CheckLine state={check} />
      <LimitsTable label={`Limits for ${provider.name}`} free={provider.free_models} paid={provider.paid_models} />
    </Card>
  );
}

type LimitRow = { free: LlmModelLimit; paid: LlmModelLimit | undefined };

const LIMIT_COLUMNS: Column<LimitRow>[] = [
  { key: "use", header: "Use", cell: (row) => row.free.tier },
  { key: "model", header: "Model", cell: (row) => row.free.model, className: "break-words" },
  { key: "free", header: "Free tier", cell: (row) => `${row.free.rpm}/min, ${row.free.rpd}/day`, className: "whitespace-nowrap" },
  {
    key: "paid",
    header: "Paid tier",
    cell: (row) => (row.paid ? `${row.paid.rpm}/min, ${row.paid.rpd}/day` : "same as free"),
    className: "whitespace-nowrap",
  },
];

function LimitsTable({ label, free, paid }: { label: string; free: LlmModelLimit[]; paid: LlmModelLimit[] }) {
  const rows = free.map((limit) => ({
    free: limit,
    paid: paid.find((item) => item.tier === limit.tier),
  }));
  return (
    <div className="mt-3">
      <DataTable
        label={label}
        columns={LIMIT_COLUMNS}
        rows={rows}
        rowKey={(row) => row.free.tier}
        empty="No models listed."
        framed={false}
        dense
        minWidth="sm"
      />
    </div>
  );
}

function KeysTable({ keys, onRevoke }: { keys: LlmManagedKey[]; onRevoke: (key: LlmManagedKey) => void }) {
  const [checks, setChecks] = useState<Record<string, CheckState>>({});
  const mutation = useMutation({
    mutationFn: (label: string) => checkLlmKey(label),
    onMutate: (label) => setChecks((current) => ({ ...current, [label]: { status: "pending" } })),
    onSuccess: (result, label) =>
      setChecks((current) => ({
        ...current,
        [label]: { status: "done", check: result },
      })),
    onError: (error, label) =>
      setChecks((current) => ({
        ...current,
        [label]: { status: "error", message: settingsErrorText(error) },
      })),
  });

  const columns: Column<LlmManagedKey>[] = [
    {
      key: "name",
      header: "Key",
      cell: (key) => (
        <div className="grid gap-0.5">
          <span className="font-medium break-all">{keyTitle(key)}</span>
          <span className="text-xs text-muted">
            {key.provider} · {maskedKey(key)}
          </span>
        </div>
      ),
    },
    {
      key: "tier",
      header: "Tier",
      cell: (key) => <Badge tone={tierTone(key.tier)}>{tierLabel(key.tier)}</Badge>,
    },
    {
      key: "source",
      header: "Source",
      cell: (key) => (
        <div className="grid gap-0.5 text-sm">
          <span>{keySourceLabel(key)}</span>
          {key.created_at !== null && (
            <span className="text-xs text-muted">
              by {key.created_by}, <RelativeTime iso={key.created_at} />
            </span>
          )}
        </div>
      ),
    },
    {
      key: "actions",
      header: "Actions",
      cell: (key) => (
        <div className="grid gap-1">
          <div className="flex flex-wrap gap-2">
            <Button
              size="sm"
              aria-label={`Check ${keyTitle(key)}`}
              disabled={checks[key.label]?.status === "pending"}
              onClick={() => mutation.mutate(key.label)}
            >
              Check
            </Button>
            {key.source === "panel" && (
              <Button size="sm" variant="danger" aria-label={`Revoke ${keyTitle(key)}`} onClick={() => onRevoke(key)}>
                Revoke
              </Button>
            )}
          </div>
          <CheckLine state={checks[key.label] ?? null} />
        </div>
      ),
    },
  ];

  return (
    <DataTable
      label="API keys"
      columns={columns}
      rows={keys}
      rowKey={(key) => key.label}
      empty="No API keys yet. Add one, or set GEMINI_API_KEYS / GROQ_API_KEYS in the NOC's environment."
    />
  );
}

function CheckLine({ state }: { state: CheckState | null }) {
  if (state === null) {
    return null;
  }
  if (state.status === "pending") {
    return (
      <p role="status" className="m-0 mt-2 text-xs text-muted">
        Checking…
      </p>
    );
  }
  if (state.status === "error") {
    return (
      <p role="alert" className="m-0 mt-2 text-xs text-critical break-words">
        {state.message}
      </p>
    );
  }
  return (
    <p role="status" className={`m-0 mt-2 text-xs break-words ${state.check.ok ? "text-ok" : "text-critical"}`}>
      {checkSummary(state.check)}
    </p>
  );
}

function RevokeKeyDialog({ llmKey, onClose }: { llmKey: LlmManagedKey | null; onClose: () => void }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const mutation = useMutation({
    mutationFn: (id: string) => revokeLlmKey(id),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [LLM_CONFIG_KEY] });
      toast.success(`Revoked ${llmKey === null ? "the key" : keyTitle(llmKey)}. Its file was deleted.`);
      onClose();
    },
  });

  return (
    <Dialog
      open={llmKey !== null}
      onOpenChange={(open) => {
        if (!open) {
          mutation.reset();
          onClose();
        }
      }}
      title={llmKey === null ? "Revoke key" : `Revoke ${keyTitle(llmKey)}?`}
      description="The NOC stops using the key within a minute and deletes its file. Revoke it at the provider as well if it may have leaked."
    >
      {llmKey !== null && (
        <div className="grid gap-4">
          {mutation.isError && (
            <p role="alert" className="m-0 text-sm text-critical">
              {settingsErrorText(mutation.error)}
            </p>
          )}
          <div className="flex flex-wrap justify-end gap-2">
            <Button variant="secondary" onClick={onClose}>
              Cancel
            </Button>
            <Button
              variant="danger"
              disabled={mutation.isPending || llmKey.id === null}
              onClick={() => {
                if (llmKey.id !== null) {
                  mutation.mutate(llmKey.id);
                }
              }}
            >
              <KeyRound aria-hidden="true" size={14} />
              Revoke key
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
