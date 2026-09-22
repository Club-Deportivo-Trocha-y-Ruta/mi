/**
 * useAthleteRaceHistory — TanStack Query hook para la progresión histórica
 * entre temporadas de un atleta (feature 044, US6/US7).
 *
 * Endpoint: GET /api/athletes/{athleteId}/race-analysis/history
 * Query key `["athlete-race-history", id]` — fija en `contracts/ui-history.md`
 * §1, sin variantes de filtro: la tarjeta no expone un selector de
 * `series_kind`, siempre pide el default del backend (`cup`).
 *
 * staleTime 5 min — mismo criterio que `useAthleteEvolution`: los datos
 * solo cambian cuando se ingesta una válida nueva o se decide una revisión
 * de identidad, no aporta refetchear constantemente.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteRaceHistory } from "@/api/raceHistory";
import { useAuthStore } from "@/store/auth.store";

export function useAthleteRaceHistory(athleteId: number | null | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const enabled =
    !!accessToken && athleteId != null && Number.isFinite(athleteId) && athleteId > 0;

  return useQuery({
    queryKey: ["athlete-race-history", athleteId ?? -1],
    queryFn: ({ signal }) =>
      getAthleteRaceHistory(athleteId as number, {}, { signal }),
    enabled,
    staleTime: 5 * 60_000,
  });
}
