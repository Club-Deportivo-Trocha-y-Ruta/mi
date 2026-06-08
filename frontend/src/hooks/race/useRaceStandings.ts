/**
 * useRaceStandings — TanStack Query hook para la clasificación general
 * de temporada (standings) a partir de un evento de carrera.
 *
 * Endpoint: GET /api/race-analysis/race-events/{id}/standings
 *
 * El backend determina la temporada/serie a partir del raceEventId, por lo
 * que el mismo event puede usarse para obtener los standings del año completo.
 *
 * Parámetros:
 *   - `raceEventId` — ID del evento. Si es null/undefined o <= 0, la query
 *     queda deshabilitada.
 *   - `filters.category_id` — filtra por categoría.
 *   - `filters.club_only` — si es true, solo retorna corredores del club.
 *
 * staleTime: 5 min — mitiga el cold start de Render Free.
 */
import { useQuery } from "@tanstack/react-query";

import { getRaceStandings } from "@/api/raceStandings";
import { useAuthStore } from "@/store/auth.store";
import { raceStandingsKeys } from "@/hooks/race/invalidation";
import type {
  RaceEventStandingsResponse,
  RaceStandingsFilters,
} from "@/types/raceResults.types";

/**
 * Hook para obtener la clasificación general de la temporada.
 *
 * @param raceEventId - ID del race event que determina la temporada.
 *   La query se deshabilita si es null, undefined, 0, o negativo.
 * @param filters - Filtros opcionales (category_id, club_only).
 */
export function useRaceStandings(
  raceEventId: number | null | undefined,
  filters: RaceStandingsFilters = {},
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const enabled =
    !!accessToken && raceEventId != null && raceEventId > 0;

  return useQuery<RaceEventStandingsResponse, unknown>({
    queryKey: raceStandingsKeys.byEventFiltered(raceEventId ?? -1, filters),
    queryFn: ({ signal }) =>
      getRaceStandings(raceEventId as number, filters, { signal }),
    enabled,
    staleTime: 5 * 60_000,
  });
}
