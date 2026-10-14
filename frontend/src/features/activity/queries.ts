import { type InfiniteData, useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { getActivity, verifyActivity } from "../../api/client";
import type { ActivityPage } from "../../api/types";
import { activityQuery, type ActivityFilters } from "./filters";

export const ACTIVITY_POLL_MS = 30_000;
export const CHAIN_CHECK_STALE_MS = 60_000;

type Feed = InfiniteData<ActivityPage, number | undefined>;

function feedKey(filters: ActivityFilters) {
  return ["activity", "feed", filters] as const;
}

export function useActivityFeed(filters: ActivityFilters) {
  const queryClient = useQueryClient();
  const feed = useInfiniteQuery({
    queryKey: feedKey(filters),
    queryFn: ({ pageParam }) => getActivity(activityQuery(filters, pageParam)),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (page) => page.next_before_id ?? undefined,
  });
  const head = useQuery({
    queryKey: ["activity", "head", filters],
    queryFn: () => getActivity(activityQuery(filters, undefined)),
    refetchInterval: ACTIVITY_POLL_MS,
  });

  const newest = head.data?.items[0]?.id;
  const shown = feed.data?.pages[0]?.items[0]?.id;
  useEffect(() => {
    if (head.data === undefined || newest === undefined || newest === shown) {
      return;
    }
    queryClient.setQueryData<Feed>(feedKey(filters), { pages: [head.data], pageParams: [undefined] });
  }, [filters, head.data, newest, queryClient, shown]);

  return feed;
}

export function useChainStatus() {
  return useQuery({
    queryKey: ["activity", "verify"],
    queryFn: () => verifyActivity(),
    staleTime: CHAIN_CHECK_STALE_MS,
  });
}
