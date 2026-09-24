/**
 * usePendingAnalyses / useDismissStaleRun — análisis IA pendientes del coach
 * (feature 045, US5), el destino de las filas «Análisis por aprobar» y
 * «Análisis desactualizados» del Home.
 *
 * Endpoints:
 *   - GET  /api/race-analysis/pending-analyses?state=&season=
 *   - POST /api/race-analysis/runs/{run_id}/dismiss-stale
 *
 * Privacidad: la queryKey lleva `state` y `season` (no PII); `athlete_ref`
 * solo vive en `data`, nunca en la clave ni en un log.
 *
 * `staleTime: 30 s`: la lista es lo que el coach está resolviendo y debe
 * reflejar aprobaciones / re-ejecuciones recientes sin recargar la página.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { dismissStaleRun, getPendingAnalyses } from "@/api/racePendingAnalyses";
import { invalidateAthleteAiQueries } from "@/hooks/ai/invalidateAthleteAiQueries";
import { useAuthStore } from "@/store/auth.store";
import type {
  PendingAnalyses,
  PendingAnalysesParams,
  PendingAnalysisState,
  RunDismissStaleResponse,
} from "@/types/racePendingAnalyses.types";

/** Raíz de las queries de esta lista (la reutiliza `invalidateAthleteAiQueries`). */
export const PENDING_ANALYSES_QUERY_BASE = "race-pending-analyses";

export const pendingAnalysesKeys = {
  all: [PENDING_ANALYSES_QUERY_BASE] as const,
  list: (state: PendingAnalysisState, season: number | null) =>
    [PENDING_ANALYSES_QUERY_BASE, state, season] as const,
};

export function usePendingAnalyses(
  params: PendingAnalysesParams,
  options: { enabled?: boolean } = {},
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const { state, season } = params;

  return useQuery<PendingAnalyses, unknown>({
    queryKey: pendingAnalysesKeys.list(state, season ?? null),
    queryFn: ({ signal }) => getPendingAnalyses({ state, season }, { signal }),
    enabled: !!accessToken && (options.enabled ?? true),
    staleTime: 30_000,
  });
}

export interface DismissStaleVariables {
  runId: string;
  /** Solo para acotar la invalidación de las queries del atleta. */
  athleteId: number;
}

export function useDismissStaleRun() {
  const queryClient = useQueryClient();

  return useMutation<RunDismissStaleResponse, unknown, DismissStaleVariables>({
    mutationKey: ["dismiss-stale-run"],
    mutationFn: ({ runId }) => dismissStaleRun(runId),
    // `onSettled` (no solo `onSuccess`): un 409 ("ya no está desactualizado")
    // también significa que el ítem dejó de pertenecer a la lista.
    // `invalidateAthleteAiQueries` cubre la lista pendiente, el resumen del
    // Home (coach-summary) y las queries del atleta / temporada.
    onSettled: (_data, _error, { athleteId }) => {
      void invalidateAthleteAiQueries(queryClient, athleteId);
    },
  });
}
