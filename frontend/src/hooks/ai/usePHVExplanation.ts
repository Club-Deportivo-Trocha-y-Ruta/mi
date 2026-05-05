import { useMutation } from "@tanstack/react-query";

import { getPHVExplanation, mapAIError } from "@/api/ai";
import type { PHVExplanationResponse } from "@/types/ai.types";

interface UsePHVExplanationVariables {
  signal?: AbortSignal;
}

/** Mutation para POST /api/ai/athletes/{id}/phv-explanation.
 *
 * Decisión de diseño: useMutation (no useQuery) porque la generación es
 * **bajo demanda** del coach, no carga al montar. El backend no persiste el
 * texto, así que no hay nada que invalidar tras éxito. El estado vive en la
 * mutación y se descarta al desmontar.
 *
 * Política de retry:
 *   - 422/403/401/502 → no reintentar (errores definitivos del cliente o
 *     guardrail; reintentar daría el mismo resultado).
 *   - 503 → hasta 2 reintentos con backoff exponencial (proveedor caído o
 *     cold start de Render).
 *   - cancelled → no reintentar.
 */
export function usePHVExplanation(athleteId: number) {
  return useMutation<
    PHVExplanationResponse,
    unknown,
    UsePHVExplanationVariables | void
  >({
    mutationKey: ["ai", "phv", athleteId],
    mutationFn: (vars) =>
      getPHVExplanation(athleteId, { signal: vars?.signal }),
    retry: (failureCount, error) => {
      const info = mapAIError(error);
      if (!info.retryable) return false;
      if (info.kind !== "disabled") return false;
      return failureCount < 2;
    },
    retryDelay: (attempt) => Math.min(5000 * 2 ** attempt, 30_000),
  });
}
