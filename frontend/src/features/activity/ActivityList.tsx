import { errorMessage } from "../../components/format";
import { Button, ErrorState, Skeleton } from "../../ui";
import { ActivityTable } from "./ActivityTable";
import type { ActivityFilters } from "./filters";
import { useActivityFeed } from "./queries";
import { emptyFeedText } from "./view";

type ActivityListProps = {
  filters: ActivityFilters;
};

export function ActivityList({ filters }: ActivityListProps) {
  const query = useActivityFeed(filters);

  if (query.data === undefined) {
    if (query.isError) {
      return (
        <ErrorState
          title="The activity log did not load"
          message={errorMessage(query.error)}
          onRetry={() => void query.refetch()}
        />
      );
    }
    return <Skeleton lines={6} />;
  }

  const entries = query.data.pages.flatMap((page) => page.items);
  return (
    <div className="grid gap-4">
      <ActivityTable entries={entries} emptyText={emptyFeedText(filters)} />
      {query.isFetchNextPageError && (
        <ErrorState
          title="Older entries did not load"
          message={errorMessage(query.error)}
          onRetry={() => void query.fetchNextPage()}
        />
      )}
      {query.hasNextPage && (
        <div>
          <Button
            variant="secondary"
            disabled={query.isFetchingNextPage}
            onClick={() => void query.fetchNextPage()}
          >
            {query.isFetchingNextPage ? "Loading…" : "Load more"}
          </Button>
        </div>
      )}
    </div>
  );
}
