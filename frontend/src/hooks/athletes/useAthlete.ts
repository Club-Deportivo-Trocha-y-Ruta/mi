import { useQuery } from "@tanstack/react-query";

import { getAthlete } from "@/api/athletes";
import { athleteKeys } from "@/api/queryKeys";

export function useAthlete(id: number, enabled = true) {
  return useQuery({
    queryKey: athleteKeys.detail(id),
    queryFn: () => getAthlete(id),
    enabled: enabled && Number.isFinite(id),
  });
}
