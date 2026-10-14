import { useQuery } from "@tanstack/react-query";
import { getTrace } from "../../api/client";
import { errorMessage } from "../../lib/format";
import { useLivePollInterval } from "../../live/useEventStream";
import { ErrorState } from "../../ui/ErrorState";
import { Section } from "../../ui/Section";
import { Skeleton } from "../../ui/Skeleton";
import { AgentRunsTimeline } from "./AgentRunsTimeline";
import { LlmCallsTable } from "./LlmCallsTable";
import { ToolCallsTable } from "./ToolCallsTable";

export function AgentActivityTab({ incidentId }: { incidentId: string }) {
  const refetchInterval = useLivePollInterval();
  const query = useQuery({
    queryKey: ["trace", incidentId],
    queryFn: () => getTrace(incidentId),
    enabled: incidentId !== "",
    refetchInterval,
  });

  if (query.isPending) {
    return <Skeleton lines={5} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="The agent activity could not be loaded"
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }

  const trace = query.data;
  return (
    <div className="grid gap-8">
      <Section heading="Agent runs">
        <AgentRunsTimeline runs={trace.agent_runs} />
      </Section>
      <Section heading="Tool calls">
        <ToolCallsTable calls={trace.tool_calls} />
      </Section>
      <Section heading="LLM calls">
        <LlmCallsTable calls={trace.llm_calls} />
      </Section>
    </div>
  );
}
