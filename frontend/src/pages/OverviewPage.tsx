import { useQuery } from "@tanstack/react-query";
import { useContext } from "react";
import { getLlmStatus, getOverview } from "../api/client";
import type { Overview } from "../api/types";
import { useSession } from "../auth/session";
import { LiveActivity } from "../features/overview/LiveActivity";
import { KpiRow } from "../features/overview/KpiRow";
import { NeedsAttention } from "../features/overview/NeedsAttention";
import { OVERVIEW_FALLBACK_POLL_MS, canCloseIncidents } from "../features/overview/model";
import { ServerList } from "../features/overview/ServerList";
import { VerdictBanner } from "../features/overview/VerdictBanner";
import { LLM_STATUS_KEY } from "../features/system/queries";
import { errorMessage } from "../lib/format";
import { StreamConnectedContext } from "../live/useEventStream";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { Card, ErrorState, PageHeader, Skeleton } from "../ui";

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

  return (
    <>
      <PageHeader title="Overview" />
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
        />
      )}
    </>
  );
}

function OverviewContent({
  overview,
  canClose,
  llmMode,
}: {
  overview: Overview;
  canClose: boolean;
  llmMode: string | undefined;
}) {
  return (
    <div className="grid gap-6">
      <VerdictBanner verdict={overview.verdict} />
      <KpiRow kpis={overview.kpis} llmMode={llmMode} />
      <Card title="Needs attention">
        <NeedsAttention items={overview.needs_attention} canClose={canClose} />
      </Card>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Live activity">
          <LiveActivity items={overview.activity} />
        </Card>
        <Card title="Servers">
          <ServerList servers={overview.servers} />
        </Card>
      </div>
    </div>
  );
}
