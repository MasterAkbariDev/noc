import { useQuery } from "@tanstack/react-query";
import { Activity, ChartColumn, HeartPulse, ListChecks, Server, UserRoundCheck } from "lucide-react";
import { useContext } from "react";
import { getLlmStatus, getMetrics, getOverview } from "../api/client";
import type { Metrics, Overview } from "../api/types";
import { useSession } from "../auth/session";
import { InProgress } from "../features/overview/InProgress";
import { IncidentTrend, OutcomeChart, RootCauseChart } from "../features/overview/Insights";
import { KpiRow } from "../features/overview/KpiRow";
import { LiveActivity } from "../features/overview/LiveActivity";
import { NeedsAttention } from "../features/overview/NeedsAttention";
import {
  OVERVIEW_FALLBACK_POLL_MS,
  TREND_DAYS,
  canCloseIncidents,
  kpiTrends,
  serverStatusCounts,
} from "../features/overview/model";
import { ServerResources } from "../features/overview/ServerResources";
import { SystemSnapshot } from "../features/overview/SystemSnapshot";
import { VerdictBanner } from "../features/overview/VerdictBanner";
import { LLM_STATUS_KEY } from "../features/system/queries";
import { errorMessage } from "../lib/format";
import { StreamConnectedContext } from "../live/useEventStream";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { ButtonLink, Card, ErrorState, PageHeader, Skeleton } from "../ui";
import { DonutChart } from "../ui/charts";

const METRICS_POLL_MS = 60_000;

export function OverviewPage() {
  useDocumentTitle("Overview");
  const { me } = useSession();
  const streamConnected = useContext(StreamConnectedContext);
  const query = useQuery({
    queryKey: ["overview"],
    queryFn: () => getOverview(),
    refetchInterval: streamConnected ? false : OVERVIEW_FALLBACK_POLL_MS,
  });
  const llm = useQuery({
    queryKey: LLM_STATUS_KEY,
    queryFn: () => getLlmStatus(),
  });
  const metrics = useQuery({
    queryKey: ["metrics", TREND_DAYS],
    queryFn: () => getMetrics(TREND_DAYS),
    refetchInterval: METRICS_POLL_MS,
  });

  return (
    <>
      <PageHeader
        eyebrow="Monitor"
        title="Overview"
        status="Live state of the servers, the incidents and the NOC itself."
        actions={
          <ButtonLink to="/stats" size="sm">
            <ChartColumn aria-hidden="true" size={14} />
            All metrics
          </ButtonLink>
        }
      />
      {query.data === undefined ? (
        query.isError ? (
          <ErrorState
            title="The overview could not be loaded."
            message={errorMessage(query.error)}
            onRetry={() => void query.refetch()}
          />
        ) : (
          <Skeleton lines={6} />
        )
      ) : (
        <OverviewContent
          overview={query.data}
          canClose={canCloseIncidents(me.role)}
          llmMode={llm.data?.mode}
          metrics={metrics.data}
          metricsFailed={metrics.isError}
        />
      )}
    </>
  );
}

type OverviewContentProps = {
  overview: Overview;
  canClose: boolean;
  llmMode: string | undefined;
  metrics: Metrics | undefined;
  metricsFailed: boolean;
};

function OverviewContent({ overview, canClose, llmMode, metrics, metricsFailed }: OverviewContentProps) {
  return (
    <div className="grid gap-6">
      <VerdictBanner verdict={overview.verdict} />
      <KpiRow kpis={overview.kpis} llmMode={llmMode} trends={kpiTrends(metrics?.per_day)} />
      <div className="grid gap-6 lg:grid-cols-3">
        <TrendSlot metrics={metrics} failed={metricsFailed} />
        <DonutChart
          title="Server status"
          subtitle="Reachability from the last Prometheus scrape"
          centerLabel={overview.servers.length === 1 ? "server" : "servers"}
          firstColumn="Status"
          valueColumn="Servers"
          empty="No server has reported yet."
          items={serverStatusCounts(overview.servers)}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="grid content-start gap-6 lg:col-span-2">
          <Card title="Needs attention" subtitle="Escalated or waiting for approval" icon={UserRoundCheck} iconTone="warning">
            <NeedsAttention items={overview.needs_attention} canClose={canClose} />
          </Card>
          <Card title="In progress" subtitle="Incidents the agents are working on" icon={ListChecks} iconTone="info">
            <InProgress />
          </Card>
        </div>
        <Card
          title="Live activity"
          subtitle="Newest first"
          icon={Activity}
          actions={
            <ButtonLink to="/activity" size="sm" variant="ghost">
              Activity log
            </ButtonLink>
          }
        >
          <LiveActivity items={overview.activity} />
        </Card>
      </div>
      <div className="grid gap-6 lg:grid-cols-3">
        <Card
          title="Servers"
          subtitle="Resource use and open incidents per server"
          icon={Server}
          className="lg:col-span-2"
          flush
          actions={
            <ButtonLink to="/servers" size="sm" variant="ghost">
              View all
            </ButtonLink>
          }
        >
          <ServerResources servers={overview.servers} />
        </Card>
        <Card
          title="NOC health"
          icon={HeartPulse}
          iconTone="ok"
          actions={
            <ButtonLink to="/system" size="sm" variant="ghost">
              Details
            </ButtonLink>
          }
        >
          <SystemSnapshot />
        </Card>
      </div>
      {metrics !== undefined && (
        <div className="grid gap-6 lg:grid-cols-2">
          <RootCauseChart metrics={metrics} />
          <OutcomeChart metrics={metrics} />
        </div>
      )}
    </div>
  );
}

function TrendSlot({ metrics, failed }: { metrics: Metrics | undefined; failed: boolean }) {
  if (metrics !== undefined) {
    return <IncidentTrend metrics={metrics} className="lg:col-span-2" />;
  }
  return (
    <Card title="Incidents over time" className="lg:col-span-2">
      {failed ? <p className="m-0 text-sm text-muted">The incident history could not be loaded.</p> : <Skeleton lines={5} />}
    </Card>
  );
}
