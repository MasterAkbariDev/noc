import type { ToolCallView } from "../api/types";

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
    return <span className="badge badge-danger">denied</span>;
  }
  if (call.ok) {
    return <span className="badge badge-ok">ok</span>;
  }
  return <span className="badge badge-danger">failed</span>;
}

export function ToolCallsTable({ calls }: { calls: ToolCallView[] }) {
  if (calls.length === 0) {
    return <p className="muted">No tool calls recorded.</p>;
  }
  return (
    <div className="tool-groups">
      {[...groupByAgent(calls)].map(([agent, group]) => (
        <section key={agent}>
          <h3>{agent}</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th scope="col">Ref</th>
                  <th scope="col">Tool</th>
                  <th scope="col">Args</th>
                  <th scope="col">Outcome</th>
                  <th scope="col">Duration</th>
                  <th scope="col">Truncated</th>
                  <th scope="col">Injection flags</th>
                </tr>
              </thead>
              <tbody>
                {group.map((call) => (
                  <tr key={call.ref}>
                    <td>
                      <code>{call.ref}</code>
                    </td>
                    <td>{call.tool}</td>
                    <td>
                      <code>{JSON.stringify(call.args)}</code>
                    </td>
                    <td>
                      <OutcomeBadge call={call} />
                      {call.decision_reason !== null && <div className="muted">{call.decision_reason}</div>}
                    </td>
                    <td>{call.duration_ms} ms</td>
                    <td>{call.truncated ? "yes" : "no"}</td>
                    <td>
                      {call.injection_flags.length > 0 && (
                        <span className="badge badge-danger">injection flags: {call.injection_flags.join(", ")}</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ))}
    </div>
  );
}
