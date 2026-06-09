/**
 * useRaceResults — TanStack Query hook para los resultados de una válida.
 *
 * Endpoint: GET /api/race-analysis/race-events/{id}/results
 *
 * Parámetros:
 *   - `raceEventId` — ID del evento. Si es null/undefined o <= 0, la query
 *     queda deshabilitada (útil durante el initial render).
 *   - `filters.category_id` — filtra por categoría específica.
 *   - `filters.club_only` — si es true, solo retorna corredores del club.
 *
 * staleTime: 5 min — mitiga el cold start de Render Free (~50 s primer request).
 * Los filtros forman parte de la query key para que cada combinación tenga
 * su propia entrada de caché.
 */
import { useQuery } from "@tanstack/react-query";

import { getRaceResults } from "@/api/raceResults";
import { useAuthStore } from "@/store/auth.store";
import { raceResultsKeys } from "@/hooks/race/invalidation";
import type {
  RaceEventResultsResponse,
  RaceResultsFilters,
} from "@/types/raceResults.types";

/**
 * Hook para obtener los resultados de una válida (tabla de llegada).
 *
 * @param raceEventId - ID del race event. La query se deshabilita si es
 *   null, undefined, 0, o negativo.
 * @param filters - Filtros opcionales (category_id, club_only).
 */
export function useRaceResults(
  raceEventId: number | null | undefined,
  filters: RaceResultsFilters = {},
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const enabled =
    !!accessToken && raceEventId != null && raceEventId > 0;

  return useQuery<RaceEventResultsResponse, unknown>({
    queryKey: raceResultsKeys.byEventFiltered(raceEventId ?? -1, filters),
    queryFn: ({ signal }) =>
      getRaceResults(raceEventId as number, filters, { signal }),
    enabled,
    staleTime: 5 * 60_000,
  });
}
