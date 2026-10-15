import type { LlmCallView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { DataTable, type Column } from "../../ui/DataTable";

export function sumTokens(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.tokens_in + call.tokens_out, 0);
}

export function sumWaitMs(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.wait_ms, 0);
}

const COLUMNS: Column<LlmCallView>[] = [
  { key: "agent", header: "Agent", cell: (call) => call.agent },
  { key: "tier", header: "Tier", cell: (call) => call.tier },
  { key: "provider", header: "Provider", cell: (call) => call.provider },
  { key: "model", header: "Model", cell: (call) => call.model },
  { key: "in", header: "Tokens in", cell: (call) => call.tokens_in, className: "tabular-nums" },
  { key: "out", header: "Tokens out", cell: (call) => call.tokens_out, className: "tabular-nums" },
  { key: "latency", header: "Latency", cell: (call) => `${call.latency_ms} ms`, className: "tabular-nums" },
  { key: "wait", header: "Wait", cell: (call) => `${call.wait_ms} ms`, className: "tabular-nums" },
  { key: "fallback", header: "Fallback", cell: (call) => (call.fallback ? <Badge tone="warning">fallback</Badge> : "-") },
  {
    key: "error",
    header: "Error",
    cell: (call) => (call.error === null ? "-" : <span className="break-all text-critical">{call.error}</span>),
  },
];

export function LlmCallsTable({ calls }: { calls: LlmCallView[] }) {
  if (calls.length === 0) {
    return <p className="m-0 text-muted">No LLM calls recorded.</p>;
  }
  return (
    <DataTable
      label="LLM calls"
      columns={COLUMNS}
      rows={calls}
      rowKey={(call) => call.id}
      empty="No LLM calls recorded."
      minWidth="lg"
      footer={[
        { key: "label", content: "Total" },
        { key: "calls", content: `${calls.length} calls` },
        { key: "skip-1", content: "-", span: 2 },
        { key: "tokens", content: `${sumTokens(calls)} tokens`, span: 2 },
        { key: "skip-2", content: "-" },
        { key: "wait", content: `${sumWaitMs(calls)} ms` },
        { key: "skip-3", content: "-", span: 2 },
      ]}
    />
  );
}
