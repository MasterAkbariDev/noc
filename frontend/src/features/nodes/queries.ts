import { useQuery } from "@tanstack/react-query";
import { getPeers } from "../../api/client";

export const PEERS_KEY = "peers";

export function usePeersQuery() {
  return useQuery({ queryKey: [PEERS_KEY], queryFn: getPeers });
}
