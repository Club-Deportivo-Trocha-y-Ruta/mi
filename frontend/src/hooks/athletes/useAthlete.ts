import { useQuery } from "@tanstack/react-query";

import { getAthlete } from "@/api/athletes";

export function useAthlete(id: number, enabled = true) {
  return useQuery({
    queryKey: ["athlete", id],
    queryFn: () => getAthlete(id),
    enabled: enabled && Number.isFinite(id),
  });
}
