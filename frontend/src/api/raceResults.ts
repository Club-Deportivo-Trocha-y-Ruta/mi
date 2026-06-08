/**
 * API client — resultados por evento (per-event finishing order).
 *
 * Endpoint cubierto:
 *   GET /api/race-analysis/race-events/{id}/results
 *
 * Auth: JWT via interceptor en apiClient.
 * RBAC: coach/admin (respuesta completa); padre (solo filas de hijos propios).
 */
import { apiClient } from "@/api/client";
import type {
  RaceEventResultsResponse,
  RaceResultsFilters,
} from "@/types/raceResults.types";

const BASE = "/api/race-analysis/race-events";

/**
 * GET /api/race-analysis/race-events/{raceEventId}/results
 *
 * Retorna la tabla de llegada del evento agrupada por categoría.
 * `category_id` y `club_only` son opcionales — ausencia = sin filtro.
 *
 * 404 si el evento no existe.
 * Padre: filas filtradas a hijos propios solamente (backend aplica el filtro).
 */
export async function getRaceResults(
  raceEventId: number,
  filters: RaceResultsFilters = {},
  options?: { signal?: AbortSignal },
): Promise<RaceEventResultsResponse> {
  const response = await apiClient.get<RaceEventResultsResponse>(
    `${BASE}/${raceEventId}/results`,
    {
      params: {
        ...(filters.category_id !== undefined && {
          category_id: filters.category_id,
        }),
        ...(filters.club_only !== undefined && {
          club_only: filters.club_only,
        }),
      },
      signal: options?.signal,
    },
  );
  return response.data;
}
