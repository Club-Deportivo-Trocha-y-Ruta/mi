/**
 * API client — clasificación general de temporada (season standings).
 *
 * Endpoint cubierto:
 *   GET /api/race-analysis/race-events/{id}/standings
 *
 * Auth: JWT via interceptor en apiClient.
 * RBAC: coach/admin (respuesta completa); padre (solo filas de hijos propios).
 */
import { apiClient } from "@/api/client";
import type {
  RaceEventStandingsResponse,
  RaceStandingsFilters,
} from "@/types/raceResults.types";

const BASE = "/api/race-analysis/race-events";

/**
 * GET /api/race-analysis/race-events/{raceEventId}/standings
 *
 * Retorna la clasificación acumulada de la temporada (desde la vista
 * `season_standings` del backend) agrupada por categoría.
 * El raceEventId determina la serie/temporada a consultar.
 *
 * `category_id` y `club_only` son opcionales — ausencia = sin filtro.
 *
 * 404 si el evento no existe o no hay standings para su serie.
 * Padre: filas filtradas a hijos propios solamente (backend aplica el filtro).
 */
export async function getRaceStandings(
  raceEventId: number,
  filters: RaceStandingsFilters = {},
  options?: { signal?: AbortSignal },
): Promise<RaceEventStandingsResponse> {
  const response = await apiClient.get<RaceEventStandingsResponse>(
    `${BASE}/${raceEventId}/standings`,
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
