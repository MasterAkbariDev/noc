import { OctagonAlert } from "lucide-react";
import type { ActionView } from "../../api/types";
import { Badge } from "../../ui/Badge";
import { DataTable, type Column } from "../../ui/DataTable";
import { List, ListItem } from "../../ui/List";
import { actionStatusLabel, plainLabel } from "./labels";

const PERMISSION_TEXT = new Map<string, string>([
  ["READ_ONLY", "Yes, it only reads"],
  ["SAFE_ACTION", "Yes, it is safe to run alone"],
  ["REQUIRES_APPROVAL", "Only with a person's approval"],
  ["BLOCKED", "Never, a person must do it"],
]);

function resourceName(resourceId: string): string {
  const separator = resourceId.indexOf(":");
  return separator === -1 ? resourceId : resourceId.slice(separator + 1);
}

export function actionTitle(action: ActionView): string {
  return `${plainLabel(action.action_type)} on ${resourceName(action.resource_id)}`;
}

function WhyNot({ action }: { action: ActionView }) {
  const reasons = action.gate_text.length > 0 ? action.gate_text : action.gate_failures.map(plainLabel);
  if (reasons.length === 0) {
    return <span className="text-muted">nothing stopped it</span>;
  }
  return (
    <List variant="bullet" gap="xs" className="text-sm">
      {reasons.map((reason, index) => (
        <ListItem key={index}>{reason}</ListItem>
      ))}
    </List>
  );
}

const COLUMNS: Column<ActionView>[] = [
  { key: "action", header: "Action", cell: (action) => actionTitle(action) },
  {
    key: "status",
    header: "Status",
    cell: (action) => <span title={action.status}>{actionStatusLabel(action.status)}</span>,
  },
  {
    key: "permission",
    header: "Can it run on its own?",
    cell: (action) => PERMISSION_TEXT.get(action.permission_class) ?? plainLabel(action.permission_class),
  },
  { key: "why", header: "Why it did not run", cell: (action) => <WhyNot action={action} /> },
  {
    key: "impact",
    header: "Risk score (higher is riskier)",
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
];

export function PolicyTable({ actions }: { actions: ActionView[] }) {
  return (
    <DataTable
      label="Actions the NOC considered"
      columns={COLUMNS}
      rows={actions}
      rowKey={(action) => `${action.action_type}-${action.resource_id}-${action.id}`}
      empty="The NOC did not consider any action."
    />
  );
}
