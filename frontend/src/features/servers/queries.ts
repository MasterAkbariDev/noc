import { useQuery } from "@tanstack/react-query";
import { getServer, getServers } from "../../api/client";

const SERVER_HEALTH_POLL_MS = 30_000;

export function useServersQuery() {
  return useQuery({
    queryKey: ["servers"],
    queryFn: () => getServers(),
    refetchInterval: SERVER_HEALTH_POLL_MS,
  });
}

export function useServerQuery(id: string) {
  return useQuery({
    queryKey: ["server", id],
    queryFn: () => getServer(id),
    refetchInterval: SERVER_HEALTH_POLL_MS,
  });
}
