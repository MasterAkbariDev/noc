import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, KeyRound, Plus, TriangleAlert, X } from "lucide-react";
import { useState } from "react";
import {
  checkAllLlmProxies,
  checkLlmKey,
  checkLlmProxy,
  getLlmConfig,
  resetLlmChain,
  revokeLlmKey,
  setLlmChain,
} from "../../api/client";
import type {
  LlmChain,
  LlmCheck,
  LlmManagedKey,
  LlmModelLimit,
  LlmChainOption,
  LlmProvider,
  LlmProxyCheck,
} from "../../api/types";
import { useSession } from "../../auth/session";
import { Badge } from "../../ui/Badge";
import { Button } from "../../ui/Button";
import { Card } from "../../ui/Card";
import { DataTable, type Column } from "../../ui/DataTable";
import { Dialog } from "../../ui/Dialog";
import { Select } from "../../ui/Form";
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
import {
  chainHeading,
  checkSummary,
  keySourceLabel,
  keyTitle,
  maskedKey,
  proxySourceLabel,
  tierLabel,
  tierTone,
} from "./view";

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
  const toast = useToast();
  const [adding, setAdding] = useState(false);
  const [proxyFor, setProxyFor] = useState<LlmProvider | null>(null);
  const [revoking, setRevoking] = useState<LlmManagedKey | null>(null);
  const [proxyChecks, setProxyChecks] = useState<Record<string, CheckState>>({});
  const checkAll = useMutation({
    mutationFn: checkAllLlmProxies,
    onMutate: () => {
      const pending: Record<string, CheckState> = {};
      for (const provider of withProxy(query.data?.providers ?? [])) {
        pending[provider.name] = { status: "pending" };
      }
      setProxyChecks(pending);
    },
    onSuccess: (results) => {
      setProxyChecks(Object.fromEntries(results.map((result) => [result.provider, { status: "done", check: result }])));
      const summary = allProxiesSummary(results);
      if (summary.ok) {
        toast.success(summary.message);
      } else {
        toast.error(summary.message);
      }
    },
    onError: (error) => {
      setProxyChecks({});
      toast.error(settingsErrorText(error));
    },
  });

  return (
    <Section heading="Language models">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="m-0 text-sm text-muted">
          API keys, proxies and the order the agents try models in. Changes reach the agents within a minute, without a
          restart.
        </p>
        <div className="flex flex-wrap gap-2">
          <Button size="sm" disabled={!query.isSuccess || checkAll.isPending} onClick={() => checkAll.mutate()}>
            Check all proxies
          </Button>
          <Button size="sm" variant="primary" disabled={!query.isSuccess} onClick={() => setAdding(true)}>
            <Plus aria-hidden="true" size={14} />
            Add API key
          </Button>
        </div>
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
              <ProviderCard
                key={provider.name}
                provider={provider}
                check={proxyChecks[provider.name] ?? null}
                onCheck={(state) => setProxyChecks((current) => ({ ...current, [provider.name]: state }))}
                onEditProxy={() => setProxyFor(provider)}
              />
            ))}
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            {query.data.chains.map((chain) => (
              <ChainCard key={chain.tier} chain={chain} options={query.data.chain_options} />
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

function withProxy(providers: LlmProvider[]): LlmProvider[] {
  return providers.filter((provider) => provider.proxy.display !== null);
}

function allProxiesSummary(results: LlmProxyCheck[]): { ok: boolean; message: string } {
  if (results.length === 0) {
    return { ok: false, message: "No provider has a proxy set, so there is nothing to check." };
  }
  const failed = results.filter((result) => !result.ok);
  if (failed.length === 0) {
    return { ok: true, message: `All ${results.length} proxies reached their provider.` };
  }
  return {
    ok: false,
    message: `${failed.length} of ${results.length} proxies failed: ${failed.map((result) => result.provider).join(", ")}.`,
  };
}

function ProviderCard({
  provider,
  check,
  onCheck,
  onEditProxy,
}: {
  provider: LlmProvider;
  check: CheckState | null;
  onCheck: (state: CheckState) => void;
  onEditProxy: () => void;
}) {
  const mutation = useMutation({
    mutationFn: () => checkLlmProxy(provider.name),
    onMutate: () => onCheck({ status: "pending" }),
    onSuccess: (result) => onCheck({ status: "done", check: result }),
    onError: (error) => onCheck({ status: "error", message: settingsErrorText(error) }),
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

function swapped(items: string[], position: number, index: number, target: number): string | undefined {
  if (position === index) {
    return items[target];
  }
  return position === target ? items[index] : undefined;
}

function ChainCard({ chain, options }: { chain: LlmChain; options: LlmChainOption[] }) {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [draft, setDraft] = useState<string[] | null>(null);
  const saved = chain.entries.map((entry) => entry.entry);
  const current = draft ?? saved;
  const labels = new Map(options.map((option) => [option.entry, option]));
  const unchanged = current.length === saved.length && current.every((entry, index) => entry === saved[index]);
  const addable = options.filter((option) => !current.includes(option.entry));

  const save = useMutation({
    mutationFn: (entries: string[]) => setLlmChain(chain.tier, entries),
    onSuccess: (config) => {
      queryClient.setQueryData([LLM_CONFIG_KEY], config);
      setDraft(null);
      toast.success(`Saved the ${chain.tier} model order.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });
  const reset = useMutation({
    mutationFn: () => resetLlmChain(chain.tier),
    onSuccess: (config) => {
      queryClient.setQueryData([LLM_CONFIG_KEY], config);
      setDraft(null);
      toast.success(`Reset the ${chain.tier} model order to providers.yaml.`);
    },
    onError: (error) => toast.error(settingsErrorText(error)),
  });

  function move(index: number, step: number) {
    const target = index + step;
    if (target < 0 || target >= current.length) {
      return;
    }
    setDraft(current.map((entry, position) => swapped(current, position, index, target) ?? entry));
  }

  return (
    <Card title={chainHeading(chain.tier)}>
      <p className="m-0 text-xs text-muted">
        {chain.customized ? "Order set in the panel." : "Order from providers.yaml."} The first model that is up is
        used. A model that is down is skipped for a while, then tried again.
      </p>
      <ol className="m-0 mt-3 grid list-none gap-2 p-0">
        {current.map((entry, index) => {
          const option = labels.get(entry);
          const name = option ? `${option.provider} · ${option.model}` : entry;
          const degraded = option !== undefined && option.model_tier !== chain.tier;
          return (
            <li
              key={entry}
              className="flex flex-wrap items-center gap-2 rounded-control border border-border px-3 py-2"
            >
              <span className="w-5 shrink-0 text-xs text-muted tabular-nums">{index + 1}.</span>
              <span className="min-w-0 flex-1 break-all text-sm">
                {name}
                {degraded && option && (
                  <Badge tone="neutral" className="ml-2">
                    {option.model_tier} tier
                  </Badge>
                )}
              </span>
              <div className="flex gap-1">
                <Button
                  size="sm"
                  aria-label={`Move ${name} up in the ${chain.tier} order`}
                  disabled={index === 0 || save.isPending}
                  onClick={() => move(index, -1)}
                >
                  <ArrowUp aria-hidden="true" size={14} />
                </Button>
                <Button
                  size="sm"
                  aria-label={`Move ${name} down in the ${chain.tier} order`}
                  disabled={index === current.length - 1 || save.isPending}
                  onClick={() => move(index, 1)}
                >
                  <ArrowDown aria-hidden="true" size={14} />
                </Button>
                <Button
                  size="sm"
                  aria-label={`Remove ${name} from the ${chain.tier} order`}
                  disabled={current.length === 1 || save.isPending}
                  onClick={() => setDraft(current.filter((_, position) => position !== index))}
                >
                  <X aria-hidden="true" size={14} />
                </Button>
              </div>
            </li>
          );
        })}
      </ol>
      {addable.length > 0 && (
        <div className="mt-3">
          <Select
            aria-label={`Add a model to the ${chain.tier} order`}
            compact
            value=""
            options={[
              { value: "", label: "Add a model to the end of the order" },
              ...addable.map((option) => ({ value: option.entry, label: `${option.provider} · ${option.model}` })),
            ]}
            onChange={(event) => {
              if (event.target.value !== "") {
                setDraft([...current, event.target.value]);
              }
            }}
          />
        </div>
      )}
      <div className="mt-3 flex flex-wrap gap-2">
        <Button
          size="sm"
          variant="primary"
          disabled={unchanged || save.isPending || reset.isPending}
          onClick={() => save.mutate(current)}
        >
          Save order
        </Button>
        <Button
          size="sm"
          disabled={(!chain.customized && draft === null) || save.isPending || reset.isPending}
          onClick={() => reset.mutate()}
        >
          Use the default order
        </Button>
        {draft !== null && (
          <Button size="sm" variant="ghost" onClick={() => setDraft(null)}>
            Discard changes
          </Button>
        )}
      </div>
    </Card>
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
