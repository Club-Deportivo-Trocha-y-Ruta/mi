/**
 * API client del módulo race-competitors (enlace retroactivo Option A R1).
 *
 * Endpoints bajo `/api/race-competitors/*`. Auth: JWT via interceptor en
 * apiClient. Cobertura: coach + admin.
 *
 * - GET    /                       → listar (unlinked filter + suggestions)
 * - GET    /{id}/suggestions       → top-N sugerencias on-demand
 * - POST   /{id}/link              → enlazar a athlete
 * - DELETE /{id}/link              → desvincular
 */
import { apiClient } from "@/api/client";
import type {
  CompetitorLinkResponse,
  CompetitorSuggestionsResponse,
  CompetitorUnlinkResponse,
  UnlinkedCompetitorsListResponse,
  UnlinkedCompetitorsParams,
} from "@/types/raceCompetitors.types";

const BASE = "/api/race-competitors";

/**
 * GET /api/race-competitors/
 *
 * Listar competitors con filtros. Para el tab "Atletas sin enlazar"
 * usar `{ unlinked: true, include_suggestions: true, suggestions_limit: 3 }`.
 */
export async function listUnlinkedCompetitors(
  params: UnlinkedCompetitorsParams = {},
  options?: { signal?: AbortSignal },
): Promise<UnlinkedCompetitorsListResponse> {
  const response = await apiClient.get<UnlinkedCompetitorsListResponse>(
    `${BASE}/`,
    {
      params: {
        unlinked: params.unlinked ?? true,
        club_filter: params.club_filter,
        season: params.season,
        include_suggestions: params.include_suggestions ?? true,
        suggestions_limit: params.suggestions_limit ?? 3,
        limit: params.limit ?? 50,
        offset: params.offset ?? 0,
      },
      signal: options?.signal,
    },
  );
  return response.data;
}

/**
 * GET /api/race-competitors/{id}/suggestions?limit=N
 *
 * Sugerencias on-demand cuando el coach quiere ver más opciones que las
 * top-3 incluidas inline en el listado.
 */
export async function getCompetitorSuggestions(
  competitorId: number,
  limit = 5,
  options?: { signal?: AbortSignal },
): Promise<CompetitorSuggestionsResponse> {
  const response = await apiClient.get<CompetitorSuggestionsResponse>(
    `${BASE}/${competitorId}/suggestions`,
    {
      params: { limit },
      signal: options?.signal,
    },
  );
  return response.data;
}

/**
 * POST /api/race-competitors/{id}/link
 *
 * Enlazar competitor a athlete. Errores esperados:
 *  - 403: coach sin permiso (athlete fuera de su club)
 *  - 404: competitor / athlete inexistente
 *  - 409: competitor ya enlazado a OTRO athlete (debe DELETE primero)
 *  - 422: athlete_id inválido (≤ 0)
 */
export async function linkCompetitor(
  competitorId: number,
  athleteId: number,
  options?: { signal?: AbortSignal },
): Promise<CompetitorLinkResponse> {
  const response = await apiClient.post<CompetitorLinkResponse>(
    `${BASE}/${competitorId}/link`,
    { athlete_id: athleteId },
    { signal: options?.signal },
  );
  return response.data;
}

/**
 * DELETE /api/race-competitors/{id}/link
 *
 * Desvincular competitor. Los RaceResult quedan sin athlete_id asociado
 * (el campo `results_propagated` reporta cuántos cambiaron).
 */
export async function unlinkCompetitor(
  competitorId: number,
  options?: { signal?: AbortSignal },
): Promise<CompetitorUnlinkResponse> {
  const response = await apiClient.delete<CompetitorUnlinkResponse>(
    `${BASE}/${competitorId}/link`,
    { signal: options?.signal },
  );
  return response.data;
}
