import { useQuery } from "@tanstack/react-query";
import { useContext } from "react";
import { getLlmStatus, getMetrics, getOverview } from "../api/client";
import type { Metrics, Overview } from "../api/types";
import { useSession } from "../auth/session";
import { FixedByNoc } from "../features/overview/FixedByNoc";
import { InProgress } from "../features/overview/InProgress";
import { IncidentTrend, OutcomeChart, RootCauseChart } from "../features/overview/Insights";
import { LiveActivity } from "../features/overview/LiveActivity";
import { NeedsAttention } from "../features/overview/NeedsAttention";
import { OVERVIEW_FALLBACK_POLL_MS, TREND_DAYS, canCloseIncidents } from "../features/overview/model";
import { ServerStrip } from "../features/overview/ServerStrip";
import { StatusHero } from "../features/overview/StatusHero";
import { SystemSnapshot } from "../features/overview/SystemSnapshot";
import { LLM_STATUS_KEY } from "../features/system/queries";
import { errorMessage } from "../lib/format";
import { StreamConnectedContext } from "../live/useEventStream";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { ButtonLink, Disclosure, ErrorState, Section, Skeleton } from "../ui";

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
  const llm = useQuery({ queryKey: LLM_STATUS_KEY, queryFn: () => getLlmStatus() });
  const metrics = useQuery({
    queryKey: ["metrics", TREND_DAYS],
    queryFn: () => getMetrics(TREND_DAYS),
    refetchInterval: METRICS_POLL_MS,
  });

  if (query.data === undefined) {
    return query.isError ? (
      <>
        <h1 className="m-0 mb-6 text-[28px] font-semibold tracking-tight">Overview</h1>
        <ErrorState
          title="The overview could not be loaded."
          message={errorMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      </>
    ) : (
      <OverviewSkeleton />
    );
  }
  return (
    <OverviewContent
      overview={query.data}
      updatedAt={new Date(query.dataUpdatedAt).toISOString()}
      canClose={canCloseIncidents(me.role)}
      replay={llm.data?.mode === "replay"}
      metrics={metrics.data}
      metricsFailed={metrics.isError}
    />
  );
}

function OverviewSkeleton() {
  return (
    <div role="status" className="grid gap-10">
      <span className="sr-only">Loading the overview…</span>
      <h1 className="sr-only">Overview</h1>
      <div aria-hidden="true" className="flex items-start gap-6">
        <span className="shimmer size-14 shrink-0 rounded-full" />
        <div className="grid flex-1 gap-3">
          <span className="shimmer block h-10 w-3/4 rounded-control" />
          <span className="shimmer block h-5 w-1/2 rounded-control" />
        </div>
      </div>
      <div aria-hidden="true" className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <span className="shimmer block h-40 rounded-card" />
        <span className="shimmer block h-40 rounded-card" />
      </div>
    </div>
  );
}

type OverviewContentProps = {
  overview: Overview;
  updatedAt: string;
  canClose: boolean;
  replay: boolean;
  metrics: Metrics | undefined;
  metricsFailed: boolean;
};

function OverviewContent({ overview, updatedAt, canClose, replay, metrics, metricsFailed }: OverviewContentProps) {
  return (
    <>
      <StatusHero verdict={overview.verdict} kpis={overview.kpis} updatedAt={updatedAt} />
      <div className="grid gap-x-12 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="min-w-0">
          {overview.needs_attention.length > 0 && (
            <Section heading="Needs you" description="The NOC stopped here and is waiting for a person.">
              <NeedsAttention items={overview.needs_attention} canClose={canClose} />
            </Section>
          )}
          <Section
            heading="Fixed by the NOC"
            description="Problems from the last 24 hours that are solved now."
            actions={
              <ButtonLink to="/incidents?filter=resolved" size="sm" variant="ghost">
                All solved incidents
              </ButtonLink>
            }
          >
            <FixedByNoc items={overview.fixed} />
          </Section>
          <Section heading="Working on it now" description="The agents are looking into these. You do not need to do anything yet.">
            <InProgress />
          </Section>
        </div>
        <aside aria-label="Servers and activity" className="min-w-0">
          <Section
            heading="Servers"
            actions={
              <ButtonLink to="/servers" size="sm" variant="ghost">
                All servers
              </ButtonLink>
            }
          >
            <ServerStrip servers={overview.servers} />
          </Section>
          <Section
            heading="Recent activity"
            actions={
              <ButtonLink to="/activity" size="sm" variant="ghost">
                Full log
              </ButtonLink>
            }
          >
            <LiveActivity items={overview.activity} />
          </Section>
        </aside>
      </div>
      <MoreDetails metrics={metrics} metricsFailed={metricsFailed} replay={replay} />
    </>
  );
}

function MoreDetails({ metrics, metricsFailed, replay }: { metrics: Metrics | undefined; metricsFailed: boolean; replay: boolean }) {
  return (
    <Disclosure summary="More details" hint="Trends, causes and the NOC's own health">
      <div className="grid gap-6">
        {replay && (
          <p className="m-0 text-sm text-muted">The AI is replaying recorded answers, so these numbers come from a demo run.</p>
        )}
        {metrics !== undefined ? (
          <>
            <IncidentTrend metrics={metrics} />
            <div className="grid gap-6 lg:grid-cols-2">
              <RootCauseChart metrics={metrics} />
              <OutcomeChart metrics={metrics} />
            </div>
          </>
        ) : metricsFailed ? (
          <p className="m-0 text-sm text-muted">The history could not be loaded. It is tried again every minute.</p>
        ) : (
          <Skeleton lines={5} />
        )}
        <Section
          heading="The NOC's own parts"
          actions={
            <ButtonLink to="/system" size="sm" variant="ghost">
              Details
            </ButtonLink>
          }
        >
          <SystemSnapshot />
        </Section>
      </div>
    </Disclosure>
  );
}
