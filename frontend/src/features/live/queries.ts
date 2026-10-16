import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { getFleetLive, getServerLive } from "../../api/client";
import type { LiveRange } from "../../api/types";
import { refreshMs } from "./range";

export function useFleetLive(range: LiveRange) {
  return useQuery({
    queryKey: ["live", "fleet", range],
    queryFn: () => getFleetLive(range),
    refetchInterval: refreshMs(range),
    placeholderData: keepPreviousData,
  });
}

export function useServerLive(id: string, range: LiveRange) {
  return useQuery({
    queryKey: ["live", "server", id, range],
    queryFn: () => getServerLive(id, range),
    refetchInterval: refreshMs(range),
    placeholderData: keepPreviousData,
    enabled: id !== "",
  });
}
