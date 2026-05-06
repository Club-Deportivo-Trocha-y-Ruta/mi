import { useQuery } from "@tanstack/react-query";

import { getAthletes } from "@/api/athletes";
import { useAuthStore } from "@/store/auth.store";

export interface AthleteFilters {
  club_id?: number;
}

export function useAthletes(filters?: AthleteFilters) {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: ["athletes", filters],
    queryFn: () => getAthletes(filters),
    enabled: !!accessToken,
  });
}
