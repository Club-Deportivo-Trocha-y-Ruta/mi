/**
 * API client — progresión histórica entre temporadas de un atleta
 * (feature 044, US6/US7).
 *
 * Endpoint: GET /api/athletes/{athlete_id}/race-analysis/history
 * Contrato: `specs/044-race-history-backfill/contracts/history-progression-api.md`.
 *
 * Auth: JWT via interceptor en `apiClient`.
 * RBAC (el backend la enforza; aquí solo describimos): admin, coach, y el
 * padre/madre del propio atleta. Nunca recibe `competitor_id` — solo
 * `athleteId`, que viene de la ruta.
 */
import { apiClient } from "@/api/client";
import type {
  AthleteRaceHistoryRead,
  RaceHistoryQueryParams,
} from "@/types/raceHistory.types";

/**
 * GET /api/athletes/{athleteId}/race-analysis/history
 *
 * `params.series_kind` — `cup` (default del backend) | `championship` | `all`.
 */
export async function getAthleteRaceHistory(
  athleteId: number,
  params: RaceHistoryQueryParams = {},
  options?: { signal?: AbortSignal },
): Promise<AthleteRaceHistoryRead> {
  const response = await apiClient.get<AthleteRaceHistoryRead>(
    `/api/athletes/${athleteId}/race-analysis/history`,
    {
      params: {
        ...(params.series_kind !== undefined && {
          series_kind: params.series_kind,
        }),
      },
      signal: options?.signal,
    },
  );
  return response.data;
}
