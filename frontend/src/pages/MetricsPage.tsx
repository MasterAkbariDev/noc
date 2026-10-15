import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { BadgeCheck, Bot, Siren, Stethoscope, Timer, UserRoundCheck, Wrench } from "lucide-react";
import { useSearchParams } from "react-router";
import { getMetrics } from "../api/client";
import type { Metrics } from "../api/types";
import {
  RANGE_OPTIONS,
  actionLabel,
  causeLabel,
  dayPoints,
  minutes,
  outcomeLabel,
  parseRange,
  percent,
  resolvedHint,
  variantLabel,
} from "../features/metrics/view";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { ColumnChart, HBarChart, LineChart, compactNumber, fullNumber } from "../ui/charts";
import { DataTable, type Column } from "../ui/DataTable";
import { Field, Select } from "../ui/Form";
import { ErrorState } from "../ui/ErrorState";
import { KpiTile } from "../ui/KpiTile";
import { PageHeader } from "../ui/PageHeader";
import { Section } from "../ui/Section";
import { Skeleton } from "../ui/Skeleton";

const SERIES_1 = "var(--ui-chart-1)";
const SERIES_2 = "var(--ui-chart-2)";
const METRICS_POLL_MS = 60_000;

export function MetricsPage() {
  useDocumentTitle("Metrics");
  const [params, setParams] = useSearchParams();
  const days = parseRange(params.get("days"));
  const query = useQuery({
    queryKey: ["metrics", days],
    queryFn: () => getMetrics(days),
    placeholderData: keepPreviousData,
    refetchInterval: METRICS_POLL_MS,
  });

  return (
    <>
      <PageHeader
        eyebrow="Insights"
        title="Metrics"
        status="How the NOC has been doing: incidents, outcomes, model use and actions."
        actions={
          <Field label="Time range" compact>
            <Select
              compact
              value={String(days)}
              options={RANGE_OPTIONS.map((option) => ({ value: String(option), label: `Last ${option} days` }))}
              onChange={(event) => setParams({ days: event.target.value }, { replace: true })}
            />
          </Field>
        }
      />
      {query.isPending && <Skeleton lines={6} />}
      {query.isError && (
        <ErrorState title="Could not load the metrics" message="Try again in a moment." onRetry={() => void query.refetch()} />
      )}
      {query.data !== undefined && (
        <div className={query.isPlaceholderData ? "opacity-60 transition-opacity" : undefined}>
          <MetricsBody metrics={query.data} />
        </div>
      )}
    </>
  );
}

function MetricsBody({ metrics }: { metrics: Metrics }) {
  const totals = metrics.totals;
  return (
    <>
      <section aria-label="Key figures" className="mb-6 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile
          label="Incidents"
          value={fullNumber(totals.incidents)}
          hint={`${totals.open} still open`}
          icon={Siren}
          trend={metrics.per_day.map((day) => day.opened)}
        />
        <KpiTile
          label="Resolved by the NOC"
          icon={BadgeCheck}
          value={percent(totals.auto_resolved_share)}
          hint={resolvedHint(metrics)}
          tone={totals.auto_resolved_share !== null && totals.auto_resolved_share >= 0.5 ? "ok" : "neutral"}
        />
        <KpiTile
          label="Diagnosis confirmed by people"
          icon={UserRoundCheck}
          value={totals.reviewed === 0 ? "–" : `${totals.confirmed} of ${totals.reviewed}`}
          hint="Checked when someone closes an incident"
        />
        <KpiTile label="Median time to resolve" value={minutes(totals.median_minutes_to_resolve)} icon={Timer} />
        <KpiTile label="Median time to diagnose" value={minutes(totals.median_minutes_to_diagnose)} icon={Stethoscope} />
        <KpiTile
          label="Model calls"
          icon={Bot}
          trend={metrics.per_day.map((day) => day.llm_calls)}
          value={compactNumber(totals.llm_calls)}
          hint={`${compactNumber(totals.tokens)} tokens, ${fullNumber(totals.llm_failures)} failed`}
        />
        <KpiTile
          label="Actions run"
          icon={Wrench}
          value={fullNumber(totals.actions_run)}
          hint={`${compactNumber(totals.tool_calls)} read-only tool calls`}
        />
      </section>
      <div className="mb-6 grid gap-4 lg:grid-cols-2">
        <ColumnChart
          title="Incidents opened per day"
          firstColumn="Day"
          series={[{ name: "Opened", color: SERIES_1 }]}
          points={dayPoints(metrics.per_day, (day) => [day.opened])}
        />
        <ColumnChart
          title="Resolved and escalated per day"
          subtitle="Resolved: fixed or recovered without a person. Escalated: handed to a person."
          firstColumn="Day"
          series={[
            { name: "Resolved", color: SERIES_1 },
            { name: "Escalated", color: SERIES_2 },
          ]}
          points={dayPoints(metrics.per_day, (day) => [day.resolved, day.escalated])}
        />
        <ColumnChart
          title="Model calls per day"
          firstColumn="Day"
          series={[{ name: "Calls", color: SERIES_1 }]}
          points={dayPoints(metrics.per_day, (day) => [day.llm_calls])}
        />
        <LineChart
          title="Tokens per day"
          subtitle="Prompt and answer tokens together"
          name="Tokens"
          color={SERIES_1}
          firstColumn="Day"
          points={dayPoints(metrics.per_day, (day) => [day.tokens])}
        />
      </div>
      <div className="mb-6 grid gap-4 lg:grid-cols-3">
        <HBarChart
          title="Root causes"
          color={SERIES_1}
          firstColumn="Root cause"
          valueColumn="Incidents"
          empty="No incidents in this range."
          items={metrics.root_causes.map((item) => ({ key: item.label, label: causeLabel(item.label), value: item.count }))}
        />
        <HBarChart
          title="Where incidents ended"
          color={SERIES_1}
          firstColumn="Status"
          valueColumn="Incidents"
          empty="No incidents in this range."
          items={metrics.outcomes.map((item) => ({ key: item.label, label: outcomeLabel(item.label), value: item.count }))}
        />
        <HBarChart
          title="Actions"
          color={SERIES_1}
          firstColumn="Result"
          valueColumn="Actions"
          empty="No actions in this range."
          items={metrics.actions.map((item) => ({ key: item.label, label: actionLabel(item.label), value: item.count }))}
        />
      </div>
      <VariantsSection metrics={metrics} />
    </>
  );
}

function VariantsSection({ metrics }: { metrics: Metrics }) {
  const columns: Column<Metrics["variants"][number]>[] = [
    { key: "variant", header: "How it was investigated", cell: (row) => variantLabel(row.variant) },
    { key: "incidents", header: "Incidents", cell: (row) => fullNumber(row.incidents) },
    { key: "resolved", header: "Resolved", cell: (row) => fullNumber(row.resolved) },
    { key: "escalated", header: "Escalated", cell: (row) => fullNumber(row.escalated) },
    {
      key: "calls",
      header: "Model calls per incident",
      cell: (row) => (row.incidents === 0 ? "–" : (row.llm_calls / row.incidents).toFixed(1)),
    },
  ];
  return (
    <Section heading="By investigation variant">
      <DataTable
        label="Incidents by investigation variant"
        columns={columns}
        rows={metrics.variants}
        rowKey={(row) => row.variant}
        empty="No incidents in this range."
      />
    </Section>
  );
}
