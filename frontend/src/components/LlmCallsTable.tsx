import type { LlmCallView } from "../api/types";

export function sumTokens(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.tokens_in + call.tokens_out, 0);
}

export function sumWaitMs(calls: LlmCallView[]): number {
  return calls.reduce((total, call) => total + call.wait_ms, 0);
}

export function LlmCallsTable({ calls }: { calls: LlmCallView[] }) {
  if (calls.length === 0) {
    return <p className="muted">No LLM calls recorded.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Agent</th>
            <th scope="col">Tier</th>
            <th scope="col">Provider</th>
            <th scope="col">Model</th>
            <th scope="col">Tokens in</th>
            <th scope="col">Tokens out</th>
            <th scope="col">Latency</th>
            <th scope="col">Wait</th>
            <th scope="col">Fallback</th>
            <th scope="col">Error</th>
          </tr>
        </thead>
        <tbody>
          {calls.map((call) => (
            <tr key={call.id}>
              <td>{call.agent}</td>
              <td>{call.tier}</td>
              <td>{call.provider}</td>
              <td>{call.model}</td>
              <td>{call.tokens_in}</td>
              <td>{call.tokens_out}</td>
              <td>{call.latency_ms} ms</td>
              <td>{call.wait_ms} ms</td>
              <td>{call.fallback ? <span className="badge badge-warn">fallback</span> : "-"}</td>
              <td>{call.error === null ? "-" : <span className="error">{call.error}</span>}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          <tr>
            <th scope="row">Total</th>
            <td>{calls.length} calls</td>
            <td colSpan={2}>-</td>
            <td colSpan={2}>{sumTokens(calls)} tokens</td>
            <td>-</td>
            <td>{sumWaitMs(calls)} ms</td>
            <td colSpan={2}>-</td>
          </tr>
        </tfoot>
      </table>
    </div>
  );
}
