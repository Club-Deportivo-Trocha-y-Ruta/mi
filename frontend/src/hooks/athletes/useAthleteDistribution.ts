/**
 * Distribución de tiempos en la categoría para un evento (FE-1).
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
  eventId: number | null | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["athlete-distribution", athleteId, season, eventId],
    queryFn: () => {
      if (!season || eventId === null || eventId === undefined) {
        throw new Error("season y event_id requeridos");
      }
      return getAthleteDistribution(athleteId, season, eventId);
    },
    enabled:
      !!accessToken &&
      Number.isFinite(athleteId) &&
      athleteId > 0 &&
      !!season &&
      eventId !== null &&
      eventId !== undefined &&
      Number.isFinite(eventId) &&
      eventId >= 1,
    staleTime: 5 * 60_000,
  });
}
