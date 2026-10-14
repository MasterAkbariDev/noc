import type { ToolCallView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { DataTable, type Column } from "../../ui/DataTable";

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
    return <Badge tone="critical">denied</Badge>;
  }
  if (call.ok) {
    return <Badge tone="ok">ok</Badge>;
  }
  return <Badge tone="critical">failed</Badge>;
}

const COLUMNS: Column<ToolCallView>[] = [
  { key: "ref", header: "Ref", cell: (call) => <code>{call.ref}</code> },
  { key: "tool", header: "Tool", cell: (call) => call.tool },
  { key: "args", header: "Args", cell: (call) => <code className="break-all text-xs">{JSON.stringify(call.args)}</code> },
  {
    key: "outcome",
    header: "Outcome",
    cell: (call) => (
      <div className="grid gap-1">
        <OutcomeBadge call={call} />
        {call.decision_reason !== null && <span className="text-xs text-muted">{call.decision_reason}</span>}
      </div>
    ),
  },
  { key: "duration", header: "Duration", cell: (call) => `${call.duration_ms} ms` },
  { key: "truncated", header: "Truncated", cell: (call) => (call.truncated ? "yes" : "no") },
  {
    key: "flags",
    header: "Injection flags",
    cell: (call) =>
      call.injection_flags.length > 0 && (
        <Badge tone="critical">injection flags: {call.injection_flags.join(", ")}</Badge>
      ),
  },
];

export function ToolCallsTable({ calls }: { calls: ToolCallView[] }) {
  if (calls.length === 0) {
    return <p className="m-0 text-muted">No tool calls recorded.</p>;
  }
  return (
    <div className="grid gap-6">
      {[...groupByAgent(calls)].map(([agent, group]) => (
        <section key={agent} className="grid gap-2">
          <h3 className="m-0 text-sm font-semibold">{agent}</h3>
          <DataTable
            label={`Tool calls by ${agent}`}
            columns={COLUMNS}
            rows={group}
            rowKey={(call) => call.ref}
            empty="No tool calls recorded."
          />
        </section>
      ))}
    </div>
  );
}
