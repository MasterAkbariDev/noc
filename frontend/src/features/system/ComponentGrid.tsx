import { CircleCheck, CircleDashed, CircleX, TriangleAlert, type LucideIcon } from "lucide-react";
import type { ComponentHealth, ComponentStatus } from "../../api/types";
import { healthView } from "../../lib/tones";
import { Card, DescriptionList, HealthBadge, KpiTile, RelativeTime } from "../../ui";

const SUMMARY_STATUSES: { status: ComponentStatus; icon: LucideIcon }[] = [
  { status: "ok", icon: CircleCheck },
  { status: "degraded", icon: TriangleAlert },
  { status: "down", icon: CircleX },
  { status: "unknown", icon: CircleDashed },
];

export function statusCount(components: ComponentHealth[], status: ComponentStatus): number {
  return components.filter((component) => component.status === status).length;
}

export function ComponentSummary({ components }: { components: ComponentHealth[] }) {
  return (
    <div aria-label="Component summary" role="group" className="grid grid-cols-2 gap-4 xl:grid-cols-4">
      {SUMMARY_STATUSES.map(({ status, icon }) => {
        const view = healthView(status);
        const count = statusCount(components, status);
        return (
          <KpiTile
            key={status}
            label={view.label}
            value={count}
            hint={count === 1 ? "component" : "components"}
            icon={icon}
            tone={count === 0 && status !== "ok" ? "neutral" : view.tone}
          />
        );
      })}
    </div>
  );
}

function DetailList({ details }: { details: Record<string, string> }) {
  const entries = Object.entries(details);
  if (entries.length === 0) {
    return null;
  }
  return (
    <DescriptionList className="mt-3" items={entries.map(([name, value]) => ({ key: name, term: name, detail: value }))} />
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
