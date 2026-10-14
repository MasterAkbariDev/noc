import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router";
import { getTrace } from "../api/client";
import { AgentRunsTimeline } from "../components/AgentRunsTimeline";
import { LlmCallsTable } from "../components/LlmCallsTable";
import { ToolCallsTable } from "../components/ToolCallsTable";
import { errorMessage } from "../components/format";
import { useLivePollInterval } from "../live/useEventStream";

export function TracePage() {
  const { id = "" } = useParams();
  const refetchInterval = useLivePollInterval();

  const query = useQuery({
    queryKey: ["trace", id],
    queryFn: () => getTrace(id),
    enabled: id !== "",
    refetchInterval,
  });

  if (query.isPending) {
    return <p className="muted">Loading trace...</p>;
  }
  if (query.isError) {
    return (
      <section>
        <Link to={`/incidents/${id}`}>Back to incident</Link>
        <p role="alert" className="error">{errorMessage(query.error)}</p>
      </section>
    );
  }

  const trace = query.data;
  return (
    <article>
      <Link to={`/incidents/${id}`}>Back to incident</Link>
      <h1>Agent trace</h1>

      <section>
        <h2>Agent runs</h2>
        <AgentRunsTimeline runs={trace.agent_runs} />
      </section>

      <section>
        <h2>Tool calls</h2>
        <ToolCallsTable calls={trace.tool_calls} />
      </section>

      <section>
        <h2>LLM calls</h2>
        <LlmCallsTable calls={trace.llm_calls} />
      </section>
    </article>
  );
}
