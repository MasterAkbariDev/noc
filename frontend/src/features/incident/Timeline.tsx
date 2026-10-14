import type { EventView } from "../../api/types";
import { RelativeTime } from "../../ui/RelativeTime";

export function Timeline({ events }: { events: EventView[] }) {
  if (events.length === 0) {
    return <p className="m-0 text-muted">No events recorded yet.</p>;
  }
  return (
    <ol className="m-0 grid list-none gap-3 p-0">
      {events.map((event, index) => (
        <li
          key={`${event.ts}-${event.type}-${index}`}
          className="timeline-item grid gap-2 rounded-card border border-border bg-surface p-3"
        >
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <strong className="font-semibold">{event.type}</strong>
            <span className="text-muted">{event.actor}</span>
            <RelativeTime iso={event.ts} className="text-muted" />
          </div>
          <code className="break-all text-xs">{JSON.stringify(event.payload)}</code>
        </li>
      ))}
    </ol>
  );
}
