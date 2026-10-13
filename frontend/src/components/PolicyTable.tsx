import type { ActionView } from "../api/types";

export function PolicyTable({ actions }: { actions: ActionView[] }) {
  if (actions.length === 0) {
    return <p className="muted">No policy decisions recorded.</p>;
  }
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Action</th>
            <th scope="col">Resource</th>
            <th scope="col">Status</th>
            <th scope="col">Permission</th>
            <th scope="col">Eligible</th>
            <th scope="col">Impact</th>
            <th scope="col">Gate failures</th>
            <th scope="col">Reasons</th>
          </tr>
        </thead>
        <tbody>
          {actions.map((action, index) => (
            <tr key={`${action.action_type}-${action.resource_id}-${index}`}>
              <td>{action.action_type}</td>
              <td>{action.resource_id}</td>
              <td>{action.status}</td>
              <td>{action.permission_class}</td>
              <td>{action.eligible ? "yes" : "no"}</td>
              <td>{action.impact_score}</td>
              <td>{action.gate_failures.join(", ") || "-"}</td>
              <td>{action.reasons.join(", ") || "-"}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
