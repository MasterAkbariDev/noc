import type { LlmCallView } from "../../api/types";
import { Badge } from "../../ui/Badge";

export function sumTokens(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.tokens_in + call.tokens_out, 0);
}

export function sumWaitMs(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.wait_ms, 0);
}

const HEADERS = ["Agent", "Tier", "Provider", "Model", "Tokens in", "Tokens out", "Latency", "Wait", "Fallback", "Error"];

export function LlmCallsTable({ calls }: { calls: LlmCallView[] }) {
  if (calls.length === 0) {
    return <p className="m-0 text-muted">No LLM calls recorded.</p>;
  }
  return (
    <div className="overflow-x-auto rounded-card border border-border bg-surface">
      <table className="m-0 w-full min-w-[40rem] border-collapse text-sm">
        <thead className="bg-surface-2 text-left text-muted">
          <tr>
            {HEADERS.map((header) => (
              <th key={header} scope="col" className="border-b border-border px-3 py-2 font-semibold">
                {header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <tr key={call.id} className="border-b border-border align-top last:border-b-0">
              <td className="px-3 py-2">{call.agent}</td>
              <td className="px-3 py-2">{call.tier}</td>
              <td className="px-3 py-2">{call.provider}</td>
              <td className="px-3 py-2">{call.model}</td>
              <td className="px-3 py-2">{call.tokens_in}</td>
              <td className="px-3 py-2">{call.tokens_out}</td>
              <td className="px-3 py-2">{call.latency_ms} ms</td>
              <td className="px-3 py-2">{call.wait_ms} ms</td>
              <td className="px-3 py-2">{call.fallback ? <Badge tone="warning">fallback</Badge> : "-"}</td>
              <td className="px-3 py-2">
                {call.error === null ? "-" : <span className="break-all text-critical">{call.error}</span>}
              </td>
            </tr>
          ))}
        </tbody>
        <tfoot className="bg-surface-2">
          <tr>
            <th scope="row" className="px-3 py-2 text-left font-semibold">
              Total
            </th>
            <td className="px-3 py-2">{calls.length} calls</td>
            <td colSpan={2} className="px-3 py-2">
              -
            </td>
            <td colSpan={2} className="px-3 py-2">
              {sumTokens(calls)} tokens
            </td>
            <td className="px-3 py-2">-</td>
            <td className="px-3 py-2">{sumWaitMs(calls)} ms</td>
            <td colSpan={2} className="px-3 py-2">
              -
            </td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
