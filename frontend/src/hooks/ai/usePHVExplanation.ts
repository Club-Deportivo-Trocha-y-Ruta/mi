import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getPHVExplanation,
  getPHVExplanationCached,
  mapAIError,
} from "@/api/ai";
import type { PHVExplanationResponse } from "@/types/ai.types";

interface UsePHVExplanationVariables {
  signal?: AbortSignal;
}

const PHV_QUERY_KEY = (athleteId: number) =>
  ["ai", "phv", athleteId] as const;

/** Query GET /api/ai/athletes/{id}/phv-explanation — caché backend.
 *
 * Devuelve `null` cuando no hay caché para la última medición (status 204).
 * El cache vive en backend (MySQL); el frontend solo lee una vez por mount
 * (`staleTime: Infinity`). Se invalida desde `useCreateAnthropometry` cuando
 * se registra una medición nueva o desde `usePHVExplanation` tras regenerar.
 */
export function usePHVExplanationCached(
  athleteId: number,
  enabled: boolean,
) {
  return useQuery<PHVExplanationResponse | null>({
    queryKey: PHV_QUERY_KEY(athleteId),
    queryFn: () => getPHVExplanationCached(athleteId),
    enabled: enabled && athleteId > 0,
    staleTime: Infinity,
    retry: false,
  });
}

/** Mutation para POST /api/ai/athletes/{id}/phv-explanation.
 *
 * Sirve tanto para "Generar" la primera vez como para "Regenerar". El
 * backend hace upsert idempotente. Tras éxito sincroniza el query del
 * caché vía `setQueryData` para evitar un GET extra.
 *
 * Política de retry:
 *   - 422/403/401/502 → no reintentar (errores definitivos del cliente o
 *     guardrail; reintentar daría el mismo resultado).
 *   - 503 → hasta 2 reintentos con backoff exponencial (proveedor caído o
 *     cold start de Render).
 *   - cancelled → no reintentar.
 */
export function usePHVExplanation(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation<
    PHVExplanationResponse,
    unknown,
    UsePHVExplanationVariables | void
  >({
    mutationKey: ["ai", "phv", "generate", athleteId],
    mutationFn: (vars) =>
      getPHVExplanation(athleteId, { signal: vars?.signal }),
    onSuccess: (data) => {
      queryClient.setQueryData(PHV_QUERY_KEY(athleteId), data);
    },
    retry: (failureCount, error) => {
      const info = mapAIError(error);
      if (!info.retryable) return false;
      if (info.kind !== "disabled") return false;
      return failureCount < 2;
    },
    retryDelay: (attempt) => Math.min(5000 * 2 ** attempt, 30_000),
  });
}
