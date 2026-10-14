import type { ComponentHealth } from "../../api/types";
import { Card, HealthBadge, RelativeTime } from "../../ui";

function DetailList({ details }: { details: Record<string, string> }) {
  const entries = Object.entries(details);
  if (entries.length === 0) {
    return null;
  }
  return (
    <dl className="m-0 mt-3 grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-sm">
      {entries.map(([name, value]) => (
        <div key={name} className="contents">
          <dt className="text-muted">{name}</dt>
          <dd className="m-0 break-words">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function ComponentCard({ component }: { component: ComponentHealth }) {
  return (
    <Card title={component.label} actions={<HealthBadge status={component.status} />}>
      <p className="m-0 text-sm break-words">{component.summary}</p>
      <DetailList details={component.details} />
      {component.since !== null && (
        <p className="m-0 mt-3 text-xs text-muted">
          Since <RelativeTime iso={component.since} />
        </p>
      )}
    </Card>
  );
}

export function ComponentGrid({ components }: { components: ComponentHealth[] }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
      {components.map((component) => (
        <ComponentCard key={component.key} component={component} />
      ))}
    </div>
  );
}
