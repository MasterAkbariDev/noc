import { Server } from "lucide-react";
import { EmptyState } from "../../ui/EmptyState";
import { ErrorState } from "../../ui/ErrorState";
import { List, ListItem } from "../../ui/List";
import { Skeleton } from "../../ui/Skeleton";
import { FleetSummary } from "./FleetSummary";
import { ServerCard } from "./ServerCard";
import { useServersQuery } from "./queries";
import { errorText } from "./serverView";

export function ServersList() {
  const query = useServersQuery();

  if (query.isPending) {
    return <Skeleton lines={4} />;
  }
  if (query.isError) {
    return (
      <ErrorState
        title="Could not load the servers"
        message={errorText(query.error)}
        onRetry={() => void query.refetch()}
      />
    );
  }
  if (query.data.length === 0) {
    return (
      <EmptyState
        icon={Server}
        title="No servers yet"
        text="Servers appear here once the NOC has an inventory for them."
      />
    );
  }
  return (
    <>
      <FleetSummary servers={query.data} />
      <List label="Server cards" gap="lg" className="sm:grid-cols-2 xl:grid-cols-3">
      {query.data.map((server) => (
        <ListItem key={server.id} className="min-w-0">
          <ServerCard server={server} />
        </ListItem>
        ))}
      </List>
    </>
  );
}
