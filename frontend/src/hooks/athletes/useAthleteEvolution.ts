/**
 * Serie temporal de una métrica del atleta dentro de una temporada
 * (FE-1).
 *
 * staleTime 5min — los datos cambian solo cuando se ingesta una
 * carrera nueva, no aporta refetchear constantemente.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteEvolution } from "@/api/athleteRaceAnalysis";
import { useAuthStore } from "@/store/auth.store";
import type { EvolutionMetric } from "@/types/athleteRaceAnalysis.types";

export function useAthleteEvolution(
  athleteId: number,
  season: number | null | undefined,
  metric: EvolutionMetric | null | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["athlete-evolution", athleteId, season, metric],
    queryFn: () => {
      if (!season || !metric) throw new Error("season y metric requeridos");
      return getAthleteEvolution(athleteId, season, metric);
    },
    enabled:
      !!accessToken &&
      Number.isFinite(athleteId) &&
      athleteId > 0 &&
      !!season &&
      !!metric,
    staleTime: 5 * 60_000,
  });
}
