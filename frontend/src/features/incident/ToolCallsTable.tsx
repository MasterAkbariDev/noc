import type { ToolCallView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { DataTable, type Column } from "../../ui/DataTable";
import { agentLabel } from "./labels";

export function groupByAgent(calls: ToolCallView[]): Map<string, ToolCallView[]> {
  const groups = new Map<string, ToolCallView[]>();
  for (const call of calls) {
    const group = groups.get(call.agent);
    if (group === undefined) {
      groups.set(call.agent, [call]);
    } else {
      group.push(call);
    }
  }
  return groups;
}

function OutcomeBadge({ call }: { call: ToolCallView }) {
  if (call.decision === "denied") {
    return <Badge tone="critical">not allowed</Badge>;
  }
  if (call.ok) {
    return <Badge tone="ok">answered</Badge>;
  }
  return <Badge tone="critical">failed</Badge>;
}

function duration(ms: number): string {
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function TechnicalDetails({ call }: { call: ToolCallView }) {
  return (
    <details className="text-xs text-muted">
      <summary className="cursor-pointer select-none">Technical details</summary>
      <p className="m-0 mt-1">
        Reference <code>{call.ref}</code>, tool <code>{call.tool}</code>
        {call.truncated && ", answer was shortened"}
      </p>
      <code dir="ltr" className="block break-all">
        {JSON.stringify(call.args)}
      </code>
    </details>
  );
}

const COLUMNS: Column<ToolCallView>[] = [
  {
    key: "what",
    header: "What it checked",
    cell: (call) => (
      <div className="grid justify-items-start gap-1">
        <span>{call.description || call.tool}</span>
        {call.injection_flags.length > 0 && (
          <Badge tone="critical">the answer contained text that tries to steer the AI</Badge>
        )}
        <TechnicalDetails call={call} />
      </div>
    ),
  },
  {
    key: "outcome",
    header: "Result",
    cell: (call) => (
      <div className="grid justify-items-start gap-1">
        <OutcomeBadge call={call} />
        {call.decision_reason !== null && <span className="text-xs text-muted">{call.decision_reason}</span>}
      </div>
    ),
  },
  { key: "duration", header: "Took", cell: (call) => duration(call.duration_ms) },
];

export function ToolCallsTable({ calls }: { calls: ToolCallView[] }) {
  if (calls.length === 0) {
    return <p className="m-0 text-muted">No checks were made on the server.</p>;
  }
  return (
    <div className="grid gap-6">
      {[...groupByAgent(calls)].map(([agent, group]) => (
        <section key={agent} className="grid gap-2">
          <h3 className="m-0 text-sm font-semibold">{agentLabel(agent)}</h3>
          <DataTable
            label={`Checks made by the ${agentLabel(agent)}`}
            columns={COLUMNS}
            rows={group}
            rowKey={(call) => call.ref}
            empty="No checks were made on the server."
          />
        </section>
      ))}
    </div>
  );
}
