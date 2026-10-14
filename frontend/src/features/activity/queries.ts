import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { getActivity, verifyActivity } from "../../api/client";
import { activityQuery, type ActivityFilters } from "./filters";

export const ACTIVITY_POLL_MS = 30_000;
export const CHAIN_CHECK_STALE_MS = 60_000;

export function useActivityFeed(filters: ActivityFilters) {
  return useInfiniteQuery({
    queryKey: ["activity", "feed", filters],
    queryFn: ({ pageParam }) => getActivity(activityQuery(filters, pageParam)),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (page) => page.next_before_id ?? undefined,
    refetchInterval: ACTIVITY_POLL_MS,
  });
}

export function useChainStatus() {
  return useQuery({
    queryKey: ["activity", "verify"],
    queryFn: () => verifyActivity(),
    staleTime: CHAIN_CHECK_STALE_MS,
  });
}
