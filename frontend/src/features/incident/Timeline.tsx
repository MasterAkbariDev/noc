import type { EventView } from "../../api/types";
import { List, ListItem } from "../../ui/List";
import { RelativeTime } from "../../ui/RelativeTime";
import { eventTypeLabel } from "./labels";

export function Timeline({ events }: { events: EventView[] }) {
  if (events.length === 0) {
    return <p className="m-0 text-muted">No events recorded yet.</p>;
  }
  return (
    <List ordered>
      {events.map((event, index) => (
        <ListItem
          key={`${event.ts}-${event.type}-${index}`}
          className="timeline-item grid gap-1 rounded-card border border-border bg-surface p-3"
        >
          <p className="m-0">{event.text || eventTypeLabel(event.type)}</p>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted">
            <RelativeTime iso={event.ts} />
            <span aria-hidden="true">·</span>
            <span>by {event.actor}</span>
          </div>
          <details className="text-xs text-muted">
            <summary className="cursor-pointer select-none">Technical details</summary>
            <p className="m-0 mt-1">
              Event <code>{event.type}</code>
            </p>
            <code dir="ltr" className="block break-all">
              {JSON.stringify(event.payload)}
            </code>
          </details>
        </ListItem>
      ))}
    </List>
  );
}
