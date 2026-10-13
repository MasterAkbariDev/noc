import { incidentStatusView } from "../lib/tones";
import { Badge } from "./Badge";
import { Term } from "./Term";

export function IncidentStatusBadge({ status }: { status: string }) {
  const view = incidentStatusView(status);
  return (
    <Badge tone={view.tone}>
      <Term technical={status}>{view.label}</Term>
    </Badge>
  );
}
