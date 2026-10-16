import { CircleCheck, Hand, Sparkles, type LucideIcon } from "lucide-react";
import type { FixedItem, FixKind } from "../../api/types";
import { AnimatedList, EmptyState, RelativeTime } from "../../ui";
import { IncidentLink } from "../incident/IncidentLink";

const KIND_VIEWS: Record<FixKind, { label: string; icon: LucideIcon }> = {
  automatic: { label: "Fixed on its own", icon: Sparkles },
  approved: { label: "Fixed after your approval", icon: Hand },
  by_itself: { label: "Went away on its own", icon: CircleCheck },
};

export function fixKindLabel(kind: FixKind): string {
  return KIND_VIEWS[kind].label;
}

const itemKey = (item: FixedItem) => item.incident_id;

export function FixedByNoc({ items }: { items: FixedItem[] }) {
  if (items.length === 0) {
    return (
      <EmptyState
        icon={CircleCheck}
        title="Nothing needed fixing in the last 24 hours."
        text="When the NOC fixes a problem on its own, it shows up here with what it did."
      />
    );
  }
  return <AnimatedList items={items} itemKey={itemKey} label="Fixed by the NOC" className="gap-1" render={(item) => <FixedRow item={item} />} />;
}

function FixedRow({ item }: { item: FixedItem }) {
  const view = KIND_VIEWS[item.kind];
  const Icon = view.icon;
  return (
    <article className="flex gap-4 rounded-card px-1 py-3">
      <span aria-hidden="true" className="mt-0.5 inline-grid size-8 shrink-0 place-items-center rounded-full bg-ok-soft text-ok">
        <Icon size={16} strokeWidth={2.25} />
      </span>
      <div className="grid min-w-0 gap-1">
        <IncidentLink id={item.incident_id} className="font-semibold break-words hover:text-accent hover:underline">
          {item.title}
        </IncidentLink>
        <p className="m-0 text-[15px] break-words">{item.sentence}</p>
        <p className="m-0 text-sm text-muted">
          {view.label} on {item.target}, <RelativeTime iso={item.resolved_at} />
        </p>
      </div>
    </article>
  );
}
