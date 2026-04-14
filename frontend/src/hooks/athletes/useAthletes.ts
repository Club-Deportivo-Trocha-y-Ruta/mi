import { useQuery } from "@tanstack/react-query";

import { getAthletes } from "@/api/athletes";

export interface AthleteFilters {
  club_id?: number;
}

export function useAthletes(filters?: AthleteFilters) {
  return useQuery({
    queryKey: ["athletes", filters],
    queryFn: () => getAthletes(filters),
  });
}
