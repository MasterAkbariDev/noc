import { useQueryClient } from "@tanstack/react-query";
import { useCallback } from "react";
import { getIncident, getStory } from "../../api/client";

export function usePrefetchIncident(): (id: string) => void {
  const queryClient = useQueryClient();
  return useCallback(
    (id: string) => {
      void queryClient.prefetchQuery({ queryKey: ["story", id], queryFn: () => getStory(id) });
      void queryClient.prefetchQuery({ queryKey: ["incident", id], queryFn: () => getIncident(id) });
    },
    [queryClient],
  );
}
