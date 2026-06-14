/**
 * API client — resultados por evento (per-event finishing order) y notas
 * del entrenador por corredor.
 *
 * Endpoints cubiertos:
 *   GET    /api/race-analysis/race-events/{id}/results
 *   PUT    /api/race-analysis/race-events/race-results/{result_id}/coach-note
 *   DELETE /api/race-analysis/race-events/race-results/{result_id}/coach-note
 *
 * Auth: JWT via interceptor en apiClient.
 * RBAC: coach/admin (respuesta completa); padre (solo filas de hijos propios).
 *       Las rutas PUT/DELETE requieren coach/admin (403 para padre).
 */
import { apiClient } from "@/api/client";
import type {
  RaceEventResultsResponse,
  RaceResultRow,
  RaceResultsFilters,
} from "@/types/raceResults.types";

const BASE = "/api/race-analysis";

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
    `${BASE}/race-events/${raceEventId}/results`,
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

/**
 * PUT /api/race-analysis/race-events/race-results/{resultId}/coach-note
 *
 * Crea o reemplaza la nota del entrenador para un corredor del club en una
 * válida específica. Idempotente: una segunda llamada reemplaza, no duplica.
 *
 * RBAC: solo coach/admin (403 para padre).
 * 422 si `coach_note` está vacío/solo espacios o supera 500 caracteres.
 * 404 si la fila no existe o fue eliminada.
 * 409/422 si la fila no tiene athlete_id (corredor no vinculado al club).
 */
export async function setResultCoachNote(
  resultId: number,
  body: { coach_note: string },
  opts?: { signal?: AbortSignal },
): Promise<RaceResultRow> {
  const { data } = await apiClient.put<RaceResultRow>(
    `${BASE}/race-events/race-results/${resultId}/coach-note`,
    body,
    { signal: opts?.signal },
  );
  return data;
}

/**
 * DELETE /api/race-analysis/race-events/race-results/{resultId}/coach-note
 *
 * Elimina la nota del entrenador para el corredor. Idempotente: si ya no hay
 * nota la respuesta sigue siendo 200 con coach_note=null.
 *
 * RBAC: solo coach/admin (403 para padre).
 * 404 si la fila no existe o fue eliminada.
 */
export async function clearResultCoachNote(
  resultId: number,
  opts?: { signal?: AbortSignal },
): Promise<RaceResultRow> {
  const { data } = await apiClient.delete<RaceResultRow>(
    `${BASE}/race-events/race-results/${resultId}/coach-note`,
    { signal: opts?.signal },
  );
  return data;
}
