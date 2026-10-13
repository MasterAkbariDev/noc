import type { EventView } from "../api/types";
import { formatTime } from "./format";

export function Timeline({ events }: { events: EventView[] }) {
  if (events.length === 0) {
    return <p className="muted">No events recorded yet.</p>;
  }
  return (
    <ol className="timeline">
      {events.map((event, index) => (
        <li key={`${event.ts}-${event.type}-${index}`} className="card timeline-item">
          <div className="finding-head">
            <strong>{event.type}</strong>
            <span className="muted">{event.actor}</span>
            <time dateTime={event.ts} className="muted">
              {formatTime(event.ts)}
            </time>
          </div>
          <code className="timeline-payload">{JSON.stringify(event.payload)}</code>
        </li>
      ))}
    </ol>
  );
}
