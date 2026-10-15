import { useSearchParams } from "react-router";
import { ActivityFilterBar } from "../features/activity/ActivityFilterBar";
import { ActivityList } from "../features/activity/ActivityList";
import { ChainBadge } from "../features/activity/ChainBadge";
import { activitySearchParams, parseActivityFilters } from "../features/activity/filters";
import { useDocumentTitle } from "../shell/useDocumentTitle";
import { PageHeader } from "../ui/PageHeader";

export function ActivityPage() {
  useDocumentTitle("Activity");
  const [params, setParams] = useSearchParams();
  const filters = parseActivityFilters(params);

  return (
    <>
      <PageHeader
        eyebrow="Insights"
        title="Activity"
        status="Who did what on the NOC, newest first: sign-ins, role changes, closed incidents and automation changes."
        actions={<ChainBadge />}
      />
      <ActivityFilterBar filters={filters} onChange={(next) => setParams(activitySearchParams(next))} />
      <ActivityList filters={filters} />
    </>
  );
}
