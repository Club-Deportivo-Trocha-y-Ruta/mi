/**
 * Lista de carreras en las que participó el atleta en una temporada (T021).
 *
 * Alimenta el picker de evento en DistributionChart — permite seleccionar
 * una carrera concreta para ver la distribución de tiempos de categoría.
 *
 * staleTime 5min: los datos cambian solo cuando se ingestan nuevas planillas.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteRaces } from "@/api/athleteRaceAnalysis";
import { useAuthStore } from "@/store/auth.store";

export function useAthleteRaces(
  athleteId: number,
  season: number | null | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["athlete-races", athleteId, season],
    queryFn: () => {
      if (!season) {
        throw new Error("season requerido");
      }
      return getAthleteRaces(athleteId, season);
    },
    enabled:
      !!accessToken &&
      Number.isFinite(athleteId) &&
      athleteId > 0 &&
      !!season,
    staleTime: 5 * 60_000,
  });
}
