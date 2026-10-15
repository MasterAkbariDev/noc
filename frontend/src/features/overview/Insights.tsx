import { causeLabel, dayPoints, outcomeLabel } from "../metrics/view";
import type { Metrics } from "../../api/types";
import { ColumnChart, DonutChart, HBarChart } from "../../ui/charts";

const SERIES = ["var(--ui-chart-1)", "var(--ui-chart-2)", "var(--ui-chart-3)"];
const OUTCOME_LIMIT = 3;
const CAUSE_LIMIT = 6;

export function IncidentTrend({ metrics, className }: { metrics: Metrics; className?: string }) {
  return (
    <ColumnChart
      title={`Incidents, last ${metrics.days} days`}
      subtitle="Opened, resolved without a person, and escalated to a person, per day"
      firstColumn="Day"
      series={[
        { name: "Opened", color: SERIES[0] ?? "" },
        { name: "Resolved", color: SERIES[2] ?? "" },
        { name: "Escalated", color: SERIES[1] ?? "" },
      ]}
      points={dayPoints(metrics.per_day, (day) => [day.opened, day.resolved, day.escalated])}
      className={className}
    />
  );
}

export function topWithOther<Item extends { label: string; count: number }>(items: Item[], limit: number): { label: string; count: number }[] {
  const sorted = [...items].sort((left, right) => right.count - left.count);
  if (sorted.length <= limit) {
    return sorted;
  }
  const rest = sorted.slice(limit).reduce((sum, item) => sum + item.count, 0);
  return [...sorted.slice(0, limit), { label: "other", count: rest }];
}

export function OutcomeChart({ metrics }: { metrics: Metrics }) {
  return (
    <DonutChart
      title="Where incidents ended"
      subtitle={`Last ${metrics.days} days`}
      centerLabel="incidents"
      firstColumn="Status"
      valueColumn="Incidents"
      empty="No incidents in this range."
      items={topWithOther(metrics.outcomes, OUTCOME_LIMIT).map((item, index) => ({
        key: item.label,
        label: outcomeLabel(item.label),
        value: item.count,
        color: SERIES[index] ?? "var(--ui-unknown)",
      }))}
    />
  );
}

export function RootCauseChart({ metrics }: { metrics: Metrics }) {
  return (
    <HBarChart
      title="Top root causes"
      subtitle={`Last ${metrics.days} days`}
      color={SERIES[0] ?? ""}
      firstColumn="Root cause"
      valueColumn="Incidents"
      empty="No incidents in this range."
      items={topWithOther(metrics.root_causes, CAUSE_LIMIT).map((item) => ({
        key: item.label,
        label: causeLabel(item.label),
        value: item.count,
      }))}
    />
  );
}
