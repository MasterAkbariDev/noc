import type { TargetView } from "../api/types";
import { formatTime } from "./format";

const RELATIVE_UNITS: [Intl.RelativeTimeFormatUnit, number][] = [
  ["year", 365 * 24 * 60 * 60 * 1000],
  ["month", 30 * 24 * 60 * 60 * 1000],
  ["day", 24 * 60 * 60 * 1000],
  ["hour", 60 * 60 * 1000],
  ["minute", 60 * 1000],
];

const relativeFormat = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

export function formatRelativeTime(iso: string, now: number): string {
  const elapsedMs = new Date(iso).getTime() - now;
  if (Number.isNaN(elapsedMs)) {
    return iso;
  }
  for (const [unit, sizeMs] of RELATIVE_UNITS) {
    if (Math.abs(elapsedMs) >= sizeMs) {
      return relativeFormat.format(Math.round(elapsedMs / sizeMs), unit);
    }
  }
  return relativeFormat.format(Math.round(elapsedMs / 1000), "second");
}

function InventoryTime({ at }: { at: string | null }) {
  if (at === null) {
    return <span className="muted">never</span>;
  }
  return (
    <time dateTime={at} title={formatTime(at)}>
      {formatRelativeTime(at, Date.now())}
    </time>
  );
}

export function TargetCard({ target }: { target: TargetView }) {
  return (
    <article className="card target-card">
      <header className="target-head">
        <h2>{target.name}</h2>
        <span className={target.environment === "prod" ? "badge badge-prod" : "badge"}>{target.environment}</span>
        {target.halted && <span className="badge badge-halted">HALTED</span>}
      </header>
      <dl className="summary">
        <dt>Automation</dt>
        <dd>{target.automation_level}</dd>
        <dt>Last inventory</dt>
        <dd>
          <InventoryTime at={target.last_inventory_at} />
        </dd>
      </dl>
      <h3>Resources</h3>
      {target.resources.length === 0 ? (
        <p className="muted">No resources inventoried.</p>
      ) : (
        <ul className="resource-list">
          {target.resources.map((resource) => (
            <li key={resource.resource_id}>
              <span className="muted">{resource.kind}</span> {resource.name}
            </li>
          ))}
        </ul>
      )}
    </article>
  );
}
