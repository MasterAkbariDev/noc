import type { LlmCallView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { agentLabel } from "./labels";
import { DataTable, type Column } from "../../ui/DataTable";

export function sumTokens(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.tokens_in + call.tokens_out, 0);
}

export function sumWaitMs(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.wait_ms, 0);
}

const COLUMNS: Column<LlmCallView>[] = [
  { key: "agent", header: "Who asked", cell: (call) => agentLabel(call.agent) },
  {
    key: "model",
    header: "AI model",
    cell: (call) => (
      <div className="grid justify-items-start gap-1">
        <span>
          {call.model} <span className="text-muted">({call.provider}, {call.tier === "strong" ? "stronger" : "faster"} model)</span>
        </span>
        {call.fallback && <Badge tone="warning">the first-choice model was busy, a backup answered</Badge>}
      </div>
    ),
  },
  {
    key: "size",
    header: "Text read / written (tokens)",
    cell: (call) => `${call.tokens_in} / ${call.tokens_out}`,
    className: "tabular-nums",
  },
  {
    key: "latency",
    header: "Took",
    cell: (call) => (call.wait_ms > 0 ? `${call.latency_ms} ms (waited ${call.wait_ms} ms for a free slot)` : `${call.latency_ms} ms`),
    className: "tabular-nums",
  },
  {
    key: "error",
    header: "Error",
    cell: (call) => (call.error === null ? "-" : <span className="break-all text-critical">{call.error}</span>),
  },
];

export function LlmCallsTable({ calls }: { calls: LlmCallView[] }) {
  if (calls.length === 0) {
    return <p className="m-0 text-muted">No AI model calls were made.</p>;
  }
  return (
    <DataTable
      label="AI model calls"
      columns={COLUMNS}
      rows={calls}
      rowKey={(call) => call.id}
      empty="No AI model calls were made."
      minWidth="lg"
      footer={[
        { key: "label", content: `Total: ${calls.length} calls` },
        { key: "skip-1", content: "-" },
        { key: "tokens", content: `${sumTokens(calls)} tokens` },
        { key: "wait", content: `waited ${sumWaitMs(calls)} ms in total` },
        { key: "skip-2", content: "-" },
      ]}
    />
  );
}
