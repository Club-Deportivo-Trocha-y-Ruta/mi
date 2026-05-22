/**
 * Distribución de tiempos en la categoría para una válida (FE-1).
 *
 * El backend devuelve pseudónimos determinísticos — nunca nombres
 * reales. staleTime 5min: los datos cambian solo al ingestar
 * nuevas planillas.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteDistribution } from "@/api/athleteRaceAnalysis";
import { useAuthStore } from "@/store/auth.store";

export function useAthleteDistribution(
  athleteId: number,
  season: number | null | undefined,
  validaNum: number | null | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["athlete-distribution", athleteId, season, validaNum],
    queryFn: () => {
      if (!season || validaNum === null || validaNum === undefined) {
        throw new Error("season y valida_num requeridos");
      }
      return getAthleteDistribution(athleteId, season, validaNum);
    },
    enabled:
      !!accessToken &&
      Number.isFinite(athleteId) &&
      athleteId > 0 &&
      !!season &&
      validaNum !== null &&
      validaNum !== undefined,
    staleTime: 5 * 60_000,
  });
}
