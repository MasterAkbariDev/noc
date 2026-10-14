import { OctagonAlert } from "lucide-react";
import type { ActionView } from "../../api/types";
import { DataTable, type Column } from "../../ui/DataTable";
import { Badge } from "../../ui/Badge";
import { actionStatusLabel } from "./labels";

const COLUMNS: Column<ActionView>[] = [
  { key: "action", header: "Action", cell: (action) => action.action_type },
  { key: "resource", header: "Resource", cell: (action) => action.resource_id },
  {
    key: "status",
    header: "Status",
    cell: (action) => <span title={action.status}>{actionStatusLabel(action.status)}</span>,
  },
  { key: "permission", header: "Permission", cell: (action) => action.permission_class },
  { key: "eligible", header: "Eligible", cell: (action) => (action.eligible ? "yes" : "no") },
  {
    key: "impact",
    header: "Impact",
    cell: (action) => (
      <span className="inline-flex flex-wrap items-center gap-2">
        {action.impact_score}
        {action.high_impact && (
          <Badge tone="critical" icon={OctagonAlert}>
            high impact
          </Badge>
        )}
      </span>
    ),
  },
  { key: "gates", header: "Gate failures", cell: (action) => action.gate_failures.join(", ") || "-" },
  { key: "reasons", header: "Reasons", cell: (action) => action.reasons.join(", ") || "-" },
];

export function PolicyTable({ actions }: { actions: ActionView[] }) {
  return (
    <DataTable
      label="Policy decisions"
      columns={COLUMNS}
      rows={actions}
      rowKey={(action) => `${action.action_type}-${action.resource_id}-${action.id}`}
      empty="No policy decisions recorded."
    />
  );
}
