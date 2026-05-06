import { useQuery } from "@tanstack/react-query";

import { getAthlete, getAthletes } from "@/api/athletes";
import { useAuthStore } from "@/store/auth.store";

export function useDashboardStats() {
  const accessToken = useAuthStore((s) => s.accessToken);

  const athletesQuery = useQuery({
    queryKey: ["athletes"],
    queryFn: () => getAthletes(),
    enabled: !!accessToken,
  });

  const athleteIds = athletesQuery.data?.items.map((a) => a.id) ?? [];

  const detailsQuery = useQuery({
    queryKey: ["dashboard-athlete-details", athleteIds],
    queryFn: () => Promise.all(athleteIds.map((id) => getAthlete(id))),
    enabled: athleteIds.length > 0,
  });

  const withAnthropometry =
    detailsQuery.data?.filter((a) => a.latest_anthropometry !== null) ?? [];

  const lastEvaluation =
    withAnthropometry
      .map((a) => a.latest_anthropometry!.evaluation_date)
      .sort((a, b) => b.localeCompare(a))[0] ?? null;

  return {
    total: athletesQuery.data?.total ?? null,
    evaluatedCount: withAnthropometry.length,
    totalCount: athleteIds.length,
    lastEvaluation,
    isLoading: athletesQuery.isPending,
    isDetailLoading: detailsQuery.isPending && athleteIds.length > 0,
  };
}
