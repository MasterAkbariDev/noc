import { useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import type { AttentionItem, Overview } from "../../api/types";
import { CloseIncidentForm } from "../../components/CloseIncidentForm";
import { withoutTitle } from "../../lib/format";
import { AnimatedList, Button, ButtonLink, Dialog, RelativeTime, SeverityBadge } from "../../ui";
import { usePrefetchIncident } from "../incident/prefetch";

type NeedsAttentionProps = {
  items: AttentionItem[];
  canClose: boolean;
};

const itemKey = (item: AttentionItem) => item.incident_id;

export function NeedsAttention({ items, canClose }: NeedsAttentionProps) {
  const queryClient = useQueryClient();
  const [resolvingId, setResolvingId] = useState<string | null>(null);
  const resolving = items.find((item) => item.incident_id === resolvingId);

  function removeFromOverview(incidentId: string) {
    queryClient.setQueryData<Overview>(["overview"], (overview) =>
      overview === undefined
        ? overview
        : { ...overview, needs_attention: overview.needs_attention.filter((item) => item.incident_id !== incidentId) },
    );
  }

  return (
    <>
      <AnimatedList
        items={items}
        itemKey={itemKey}
        label="Incidents that need you"
        className="gap-3"
        render={(item) => (
          <AttentionRow
            item={item}
            canResolve={canClose && item.status === "ESCALATED"}
            onResolve={() => setResolvingId(item.incident_id)}
          />
        )}
      />
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
            onClosed={() => {
              removeFromOverview(resolving.incident_id);
              setResolvingId(null);
            }}
          />
        )}
      </Dialog>
    </>
  );
}

function AttentionRow({ item, canResolve, onResolve }: { item: AttentionItem; canResolve: boolean; onResolve: () => void }) {
  const waitingForApproval = item.status === "AWAITING_APPROVAL";
  const prefetch = usePrefetchIncident();
  return (
    <article className="lift grid gap-3 rounded-card border border-border border-l-4 border-l-warning bg-surface p-4 shadow-card sm:flex sm:items-center sm:justify-between">
      <div className="grid min-w-0 gap-1">
        <h3 className="m-0 text-base leading-snug font-semibold break-words">{item.title}</h3>
        <p className="m-0 text-sm text-muted break-words">{withoutTitle(item.title, item.summary)}</p>
        <p className="m-0 flex flex-wrap items-center gap-x-2 text-sm text-muted">
          <SeverityBadge severity={item.severity} />
          <span>
            {item.target}, {waitingForApproval ? "waiting for approval since" : "waiting since"} <RelativeTime iso={item.since} />
          </span>
        </p>
      </div>
      <div className="flex shrink-0 flex-wrap gap-2">
        <ButtonLink
          to={`/incidents/${encodeURIComponent(item.incident_id)}`}
          variant="primary"
          onMouseEnter={() => prefetch(item.incident_id)}
          onFocus={() => prefetch(item.incident_id)}
        >
          {waitingForApproval ? "Review and approve" : "See the steps"}
        </ButtonLink>
        {canResolve && <Button onClick={onResolve}>Mark resolved</Button>}
      </div>
    </article>
  );
}
