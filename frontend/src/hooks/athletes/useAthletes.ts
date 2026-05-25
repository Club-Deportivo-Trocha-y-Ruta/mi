import { useQuery } from "@tanstack/react-query";

import { getAthletes } from "@/api/athletes";
import { athleteKeys } from "@/api/queryKeys";
import { useAuthStore } from "@/store/auth.store";

export interface AthleteFilters {
  club_id?: number;
}

export function useAthletes(filters?: AthleteFilters) {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: athleteKeys.list(filters),
    queryFn: () => getAthletes(filters),
    enabled: !!accessToken,
  });
}
