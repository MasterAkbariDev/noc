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
    <article className="lift grid gap-3 rounded-card border border-border bg-surface p-5 shadow-card">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
        <SeverityBadge severity={item.severity} />
        <span>
          {item.target}, {waitingForApproval ? "waiting for approval since" : "waiting for you since"} <RelativeTime iso={item.since} />
        </span>
      </div>
      <div className="grid gap-1">
        <h3 className="m-0 text-lg leading-snug font-semibold break-words">{item.title}</h3>
        <p className="m-0 text-muted break-words">{withoutTitle(item.title, item.summary)}</p>
      </div>
      <p className="m-0 border-l-2 border-accent pl-3 break-words">
        <span className="font-semibold">What to do: </span>
        {item.advice}
      </p>
      <div className="flex flex-wrap gap-2">
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
