import { useMemo } from "react";
import { Activity } from "lucide-react";
import { Link } from "react-router";
import type { ActivityItem } from "../../api/types";
import { cx } from "../../lib/cx";
import { AnimatedList, EmptyState, RelativeTime } from "../../ui";
import { recentActivity } from "./model";

export function LiveActivity({ items }: { items: ActivityItem[] }) {
  const recent = useMemo(() => recentActivity(items), [items]);
  if (recent.length === 0) {
    return <EmptyState icon={Activity} title="Nothing has happened yet." text="Sign-ins, alerts and fixes appear here as they happen." />;
  }
  return (
    <AnimatedList
      items={recent}
      itemKey={activityKey}
      label="Recent activity"
      className="relative before:absolute before:inset-y-2 before:left-[3px] before:w-px before:bg-border before:content-['']"
      itemClassName="relative grid gap-0.5 py-2 pl-5 text-[15px]"
      render={(item) => (
        <>
          <span
            aria-hidden="true"
            className={cx("absolute top-[0.95rem] left-0 size-[7px] rounded-full", item.kind === "incident" ? "bg-accent" : "bg-border-strong")}
          />
          <ActivityText item={item} />
          <RelativeTime iso={item.ts} className="text-sm text-muted" />
        </>
      )}
    />
  );
}

const activityKey = (item: ActivityItem) => `${item.ts}-${item.kind}-${item.text}`;

function ActivityText({ item }: { item: ActivityItem }) {
  if (item.incident_id === null) {
    return <span className="min-w-0 break-words">{item.text}</span>;
  }
  return (
    <Link
      to={`/incidents/${encodeURIComponent(item.incident_id)}`}
      className="min-w-0 break-words font-medium hover:text-accent hover:underline"
    >
      {item.text}
    </Link>
  );
}
