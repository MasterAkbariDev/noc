import { useQuery } from "@tanstack/react-query";
import { getPeers } from "../../api/client";

export const PEERS_KEY = "peers";

const PEERS_POLL_MS = 30_000;

export function usePeersQuery() {
  return useQuery({ queryKey: [PEERS_KEY], queryFn: getPeers, refetchInterval: PEERS_POLL_MS });
}
