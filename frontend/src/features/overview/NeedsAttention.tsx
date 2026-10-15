import { CircleCheck } from "lucide-react";
import { useState } from "react";
import type { AttentionItem } from "../../api/types";
import { CloseIncidentForm } from "../../components/CloseIncidentForm";
import { incidentStatusView } from "../../lib/tones";
import { Badge, Button, ButtonLink, Dialog, EmptyState, List, ListItem, RelativeTime, SeverityBadge } from "../../ui";
import { usePrefetchIncident } from "../incident/prefetch";

type NeedsAttentionProps = {
  items: AttentionItem[];
  canClose: boolean;
};

export function NeedsAttention({ items, canClose }: NeedsAttentionProps) {
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const resolving = items.find((item) => item.incident_id === resolvingId);

  if (items.length === 0) {
    return <EmptyState icon={CircleCheck} title="Nothing needs you right now." />;
  }

  return (
    <>
      <List>
        {items.map((item) => (
          <AttentionRow
            key={item.incident_id}
            item={item}
            canResolve={canClose && item.status === "ESCALATED"}
            onResolve={() => setResolvingId(item.incident_id)}
          />
        ))}
      </List>
      <Dialog
        open={resolving !== undefined}
        onOpenChange={(open) => {
          if (!open) {
            setResolvingId(null);
          }
        }}
        title="Mark incident resolved"
      >
        {resolving !== undefined && (
          <CloseIncidentForm
            incidentId={resolving.incident_id}
            status={resolving.status}
            onClosed={() => setResolvingId(null)}
          />
        )}
      </Dialog>
    </>
  );
}

function AttentionRow({
  item,
  canResolve,
  onResolve,
}: {
  item: AttentionItem;
  canResolve: boolean;
  onResolve: () => void;
}) {
  const sinceLead = item.status === "ESCALATED" ? "Escalated " : "Waiting for approval since ";
  const prefetch = usePrefetchIncident();
  return (
    <ListItem className="grid gap-2 rounded-control border border-border border-l-4 border-l-warning bg-surface p-4">
      <div className="flex flex-wrap items-center gap-2">
        <SeverityBadge severity={item.severity} />
        <Badge tone={incidentStatusView(item.status).tone}>{item.status_label}</Badge>
        <span className="text-sm text-muted">
          {sinceLead}
          <RelativeTime iso={item.since} />
        </span>
      </div>
      <h3 className="m-0 text-base font-semibold break-words">{item.title}</h3>
      <p className="m-0 text-sm text-muted">{item.target}</p>
      <p className="m-0">{item.summary}</p>
      <p className="m-0 text-sm">
        <span className="font-semibold">What to do: </span>
        {item.advice}
      </p>
      <div className="flex flex-wrap gap-2">
        <ButtonLink
          to={`/incidents/${encodeURIComponent(item.incident_id)}`}
          size="sm"
          onMouseEnter={() => prefetch(item.incident_id)}
          onFocus={() => prefetch(item.incident_id)}
        >
          {item.status === "AWAITING_APPROVAL" ? "Review and approve" : "Open"}
        </ButtonLink>
        {canResolve && (
          <Button variant="primary" size="sm" onClick={onResolve}>
            Mark resolved
          </Button>
        )}
      </div>
    </ListItem>
  );
}
