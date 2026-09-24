/**
 * API client — análisis IA pendientes del coach (feature 045, US5).
 *
 * Contrato: `specs/045-competitions-one-place/contracts/api.md`.
 * Auth: JWT via interceptor en `apiClient`. Solo coach/admin.
 */
import { apiClient } from "@/api/client";
import type {
  PendingAnalyses,
  PendingAnalysesParams,
  RunDismissStaleResponse,
} from "@/types/racePendingAnalyses.types";

const BASE = "/api/race-analysis";

/** GET /api/race-analysis/pending-analyses — `state` es obligatorio (422 si falta). */
export async function getPendingAnalyses(
  params: PendingAnalysesParams,
  options?: { signal?: AbortSignal },
): Promise<PendingAnalyses> {
  const response = await apiClient.get<PendingAnalyses>(`${BASE}/pending-analyses`, {
    params: {
      state: params.state,
      ...(params.season !== undefined && { season: params.season }),
    },
    signal: options?.signal,
  });
  return response.data;
}

/**
 * POST /api/race-analysis/runs/{runId}/dismiss-stale — el coach decide que el
 * análisis sigue siendo válido pese a la re-ingesta. 409 si el run no está
 * desactualizado. No re-ejecuta nada.
 */
export async function dismissStaleRun(runId: string): Promise<RunDismissStaleResponse> {
  const response = await apiClient.post<RunDismissStaleResponse>(
    `${BASE}/runs/${encodeURIComponent(runId)}/dismiss-stale`,
  );
  return response.data;
}
