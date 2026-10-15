import { useQuery } from "@tanstack/react-query";
import { getSystemHealth } from "../../api/client";
import { errorMessage } from "../../lib/format";
import { ErrorState, HealthBadge, List, ListItem, Skeleton } from "../../ui";
import { SYSTEM_HEALTH_KEY, SYSTEM_POLL_MS } from "../system/queries";

export function SystemSnapshot() {
  const query = useQuery({
    queryKey: SYSTEM_HEALTH_KEY,
    queryFn: () => getSystemHealth(),
    refetchInterval: SYSTEM_POLL_MS,
  });
  if (query.isPending) {
    return <Skeleton lines={4} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="System health could not be loaded."
        message={errorMessage(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  return (
    <List variant="divided" label="NOC components">
      {query.data.components.map((component) => (
        <ListItem key={component.key} className="flex items-start justify-between gap-3">
          <span className="grid min-w-0 gap-0.5">
            <span className="text-sm font-medium">{component.label}</span>
            <span className="text-xs break-words text-muted">{component.summary}</span>
          </span>
          <HealthBadge status={component.status} />
        </ListItem>
      ))}
    </List>
  );
}
