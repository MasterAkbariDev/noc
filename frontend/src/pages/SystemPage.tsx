import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { getLlmStatus, getSystemHealth } from "../api/client";
import type { SystemHealth } from "../api/types";
import { ComponentGrid, ComponentSummary } from "../features/system/ComponentGrid";
import { LlmPanel } from "../features/system/LlmPanel";
import { QueryBody } from "../features/system/QueryBody";
import { StuckIncidents } from "../features/system/StuckIncidents";
import { LLM_STATUS_KEY, SYSTEM_HEALTH_KEY, SYSTEM_POLL_MS } from "../features/system/queries";
import { verdictView } from "../features/system/view";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader, RelativeTime, Section } from "../ui";

function verdictStatus(query: UseQueryResult<SystemHealth, Error>): ReactNode {
  if (query.isSuccess) {
    return (
      <>
        {verdictView(query.data.verdict).label}. Checked <RelativeTime iso={query.data.checked_at} />
      </>
    );
  }
  if (query.isError) {
    return "Status unavailable";
  }
  return "Checking…";
}

export function SystemPage() {
  useDocumentTitle("System");

  const health = useQuery({
    queryKey: SYSTEM_HEALTH_KEY,
    queryFn: () => getSystemHealth(),
    refetchInterval: SYSTEM_POLL_MS,
  });

  const llm = useQuery({
    queryKey: LLM_STATUS_KEY,
    queryFn: () => getLlmStatus(),
    refetchInterval: SYSTEM_POLL_MS,
  });

  return (
    <>
      <PageHeader title="System" status={verdictStatus(health)} />
      <Section heading="Components">
        <QueryBody query={health} failure="System health did not load">
          {(data) => (
            <>
              <ComponentSummary components={data.components} />
              <ComponentGrid components={data.components} />
            </>
          )}
        </QueryBody>
      </Section>
      <Section heading="Language models">
        <QueryBody query={llm} failure="LLM status did not load">
          {(status) => <LlmPanel status={status} />}
        </QueryBody>
      </Section>
      <Section heading="Stuck incidents">
        <QueryBody query={health} failure="Stuck incidents did not load">
          {(data) => <StuckIncidents incidents={data.stuck_incidents} />}
        </QueryBody>
      </Section>
    </>
  );
}
