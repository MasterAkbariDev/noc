import { Activity } from "lucide-react";
import { Link } from "react-router";
import type { ActivityItem } from "../../api/types";
import { cx } from "../../lib/cx";
import { EmptyState, List, ListItem, RelativeTime } from "../../ui";
import { recentActivity } from "./model";

export function LiveActivity({ items }: { items: ActivityItem[] }) {
  const recent = recentActivity(items);
  if (recent.length === 0) {
    return <EmptyState icon={Activity} title="No activity yet." />;
  }
  return (
    <List ordered gap="xs" className="relative before:absolute before:inset-y-1 before:left-[3px] before:w-px before:bg-border before:content-['']">
      {recent.map((item) => (
        <ListItem key={`${item.ts}-${item.kind}-${item.text}`} className="relative grid gap-0.5 py-1.5 pl-5 text-sm">
          <span
            aria-hidden="true"
            className={cx("absolute top-3 left-0 size-[7px] rounded-full", item.kind === "incident" ? "bg-accent" : "bg-muted")}
          />
          <ActivityText item={item} />
          <RelativeTime iso={item.ts} className="text-xs text-muted" />
        </ListItem>
      ))}
    </List>
  );
}

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
