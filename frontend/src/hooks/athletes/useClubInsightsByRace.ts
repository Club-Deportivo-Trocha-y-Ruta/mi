/**
 * Hook TanStack Query para la vista cross-atleta por válida (Sprint 3).
 *
 * Obtiene todos los insights del club para un race_event_id dado.
 * El RBAC lo aplica el backend:
 *   - Coach: nombres reales + confidence + excerpts.
 *   - Parent: solo su hijo con datos; otros → athlete_id=0, sin excerpt.
 *   - Admin: requiere club_id explícito.
 *
 * El hook queda deshabilitado si raceEventId es null o NaN.
 */
import { useQuery } from "@tanstack/react-query";

import { getClubInsightsByRace } from "@/api/athleteRaceAnalysis";
import type { ClubInsightsByRaceOpts } from "@/api/athleteRaceAnalysis";

export function useClubInsightsByRace(
  raceEventId: number | null,
  opts?: ClubInsightsByRaceOpts,
) {
  return useQuery({
    queryKey: [
      "club-insights-by-race",
      raceEventId,
      opts?.clubId,
      opts?.latestOnly,
      opts?.limit,
    ],
    queryFn: () => getClubInsightsByRace(raceEventId!, opts ?? {}),
    enabled: raceEventId !== null && !Number.isNaN(raceEventId),
    staleTime: 60_000,
  });
}
