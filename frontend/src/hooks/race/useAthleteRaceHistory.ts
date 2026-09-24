/**
 * useAthleteRaceHistory — TanStack Query hook para la progresión histórica
 * entre temporadas de un atleta (feature 044, US6/US7).
 *
 * Endpoint: GET /api/athletes/{athleteId}/race-analysis/history
 * Query key `["athlete-race-history", id, seriesKind]` — el prefijo
 * `["athlete-race-history", id]` de `contracts/ui-history.md` §1 se conserva,
 * así que invalidar por atleta sigue alcanzando todas las variantes.
 *
 * `seriesKind` (feature 045, T035): `"cup"` (default — los llamadores
 * existentes no cambian y no envían el parámetro, el backend asume `cup`),
 * `"championship"` o `"all"`. «Progresión» pide `"all"` y separa en cliente
 * las copas (la línea) de los campeonatos (tarjetas de lectura).
 *
 * staleTime 5 min — mismo criterio que `useAthleteEvolution`: los datos
 * solo cambian cuando se ingesta una válida nueva o se decide una revisión
 * de identidad, no aporta refetchear constantemente.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteRaceHistory } from "@/api/raceHistory";
import { useAuthStore } from "@/store/auth.store";
import type { RaceHistorySeriesKind } from "@/types/raceHistory.types";

export function useAthleteRaceHistory(
  athleteId: number | null | undefined,
  seriesKind: RaceHistorySeriesKind = "cup",
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const enabled =
    !!accessToken && athleteId != null && Number.isFinite(athleteId) && athleteId > 0;

  return useQuery({
    queryKey: ["athlete-race-history", athleteId ?? -1, seriesKind],
    queryFn: ({ signal }) =>
      getAthleteRaceHistory(
        athleteId as number,
        seriesKind === "cup" ? {} : { series_kind: seriesKind },
        { signal },
      ),
    enabled,
    staleTime: 5 * 60_000,
  });
}
