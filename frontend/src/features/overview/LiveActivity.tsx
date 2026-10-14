import { Activity } from "lucide-react";
import { Link } from "react-router";
import type { ActivityItem } from "../../api/types";
import { EmptyState, RelativeTime } from "../../ui";
import { recentActivity } from "./model";

export function LiveActivity({ items }: { items: ActivityItem[] }) {
  const recent = recentActivity(items);
  if (recent.length === 0) {
    return <EmptyState icon={Activity} title="No activity yet." />;
  }
  return (
    <ol className="m-0 grid list-none gap-2 p-0">
      {recent.map((item) => (
        <li key={`${item.ts}-${item.kind}-${item.text}`} className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm">
          <RelativeTime iso={item.ts} className="shrink-0 text-muted" />
          <ActivityText item={item} />
        </li>
      ))}
    </ol>
  );
}

function ActivityText({ item }: { item: ActivityItem }) {
  if (item.incident_id === null) {
    return <span className="min-w-0 break-words">{item.text}</span>;
  }
  return (
    <Link
      to={`/incidents/${encodeURIComponent(item.incident_id)}`}
      className="min-w-0 break-words underline underline-offset-4"
    >
      {item.text}
    </Link>
  );
}
