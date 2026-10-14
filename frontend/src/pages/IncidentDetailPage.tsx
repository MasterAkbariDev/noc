import { useQuery, type UseQueryResult } from "@tanstack/react-query";
import { useState, type ReactNode } from "react";
import { Link, useParams, useSearchParams } from "react-router";
import { getIncident, getServers, getStory } from "../api/client";
import type { IncidentDetail, ServerSummary } from "../api/types";
import { useSession } from "../auth/session";
import { CloseIncidentForm } from "../components/CloseIncidentForm";
import { errorMessage } from "../lib/format";
import { AgentActivityTab } from "../features/incident/AgentActivityTab";
import { ApprovalCard } from "../features/incident/ApprovalCard";
import { canDecideActions, pendingApprovals } from "../features/incident/approval";
import { EvidenceTab } from "../features/incident/EvidenceTab";
import { ReportTab } from "../features/incident/ReportTab";
import { StoryHeader } from "../features/incident/StoryHeader";
import { StoryProgress } from "../features/incident/StoryProgress";
import { StorySections } from "../features/incident/StorySections";
import { TimelineTab } from "../features/incident/TimelineTab";
import { useLivePollInterval } from "../live/useEventStream";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { Dialog } from "../ui/Dialog";
import { ErrorState } from "../ui/ErrorState";
import { Skeleton } from "../ui/Skeleton";
import { Tabs, type TabItem } from "../ui/Tabs";

const TAB_IDS = ["evidence", "activity", "report", "timeline"] as const;
type TabId = (typeof TAB_IDS)[number];

function tabFrom(value: string | null): TabId {
  return TAB_IDS.find((tab) => tab === value) ?? "evidence";
}

function serverIdFor(servers: ServerSummary[] | undefined, target: string): string | null {
  return servers?.find((server) => server.name === target)?.id ?? null;
}

function BackLink() {
  return (
    <Link to="/incidents" className="justify-self-start text-sm text-accent underline">
      Back to incidents
    </Link>
  );
}

function detailPart(
  query: UseQueryResult<IncidentDetail, Error>,
  render: (incident: IncidentDetail) => ReactNode,
): ReactNode {
  if (query.isPending) {
    return <Skeleton lines={5} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="The incident details could not be loaded"
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return render(query.data);
}

export function IncidentDetailPage() {
  const { id = "" } = useParams();
  const { me } = useSession();
  const [searchParams, setSearchParams] = useSearchParams();
  const [closing, setClosing] = useState(false);
  const refetchInterval = useLivePollInterval();

  const story = useQuery({
    queryKey: ["story", id],
    queryFn: () => getStory(id),
    enabled: id !== "",
    refetchInterval,
  });
  const incident = useQuery({
    queryKey: ["incident", id],
    queryFn: () => getIncident(id),
    enabled: id !== "",
    refetchInterval,
  });
  const servers = useQuery({ queryKey: ["servers"], queryFn: getServers });
  useDocumentTitle(story.data?.title ?? "Incident");

  if (story.isPending) {
    return (
      <div className="grid gap-6">
        <BackLink />
        <Skeleton lines={6} />
      </div>
    );
  }
  if (story.isError) {
    return (
      <div className="grid gap-6">
        <BackLink />
        <ErrorState
          title="This incident could not be loaded"
          message={errorMessage(story.error)}
          onRetry={() => void story.refetch()}
        />
      </div>
    );
  }

  const data = story.data;
  const canClose = data.status === "ESCALATED" && me.role !== "viewer";
  const canDecide = canDecideActions(me.role);
  const approvals = pendingApprovals(incident.data?.actions ?? []);
  const tab = tabFrom(searchParams.get("tab"));

  function selectTab(value: string) {
    setSearchParams(
      (previous) => {
        const next = new URLSearchParams(previous);
        next.set("tab", value);
        return next;
      },
      { replace: true },
    );
  }

  const items: TabItem[] = [
    {
      value: "evidence",
      label: "Evidence",
      content: detailPart(incident, (detail) => <EvidenceTab incident={detail} />),
    },
    { value: "activity", label: "Agent activity", content: <AgentActivityTab incidentId={id} /> },
    {
      value: "report",
      label: "Report",
      content: detailPart(incident, (detail) => <ReportTab report={detail.report_markdown} />),
    },
    {
      value: "timeline",
      label: "Timeline",
      content: detailPart(incident, (detail) => <TimelineTab events={detail.events} />),
    },
  ];

  return (
    <div className="grid gap-8">
      <BackLink />
      <StoryHeader
        story={data}
        openedAt={incident.data?.opened_at ?? null}
        serverId={serverIdFor(servers.data, data.target)}
      />
      <StoryProgress steps={data.steps} />
      <StorySections story={data} onClose={canClose ? () => setClosing(true) : undefined} />
      {approvals.map((action) => (
        <ApprovalCard key={action.id} incidentId={id} action={action} canDecide={canDecide} />
      ))}
      <Tabs label="Incident details" items={items} value={tab} onValueChange={selectTab} />
      {canClose && (
        <Dialog open={closing} onOpenChange={setClosing} title="Close this incident">
          <CloseIncidentForm incidentId={id} status={data.status} onClosed={() => setClosing(false)} />
        </Dialog>
      )}
    </div>
  );
}
