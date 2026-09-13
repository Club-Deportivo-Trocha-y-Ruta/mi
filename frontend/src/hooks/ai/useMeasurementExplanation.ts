import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getMeasurementExplanationCached,
  mapAIError,
  postMeasurementExplanation,
  type PHVAudience,
} from "@/api/ai";
import type { AnthropometricRecordExplanationResponse } from "@/types/ai.types";

interface MeasurementExplanationVariables {
  signal?: AbortSignal;
}

// Feature 042 (T043/T072): igual criterio de partición de caché que
// `usePHVExplanation.ts::PHV_QUERY_KEY` — "family" y "coach" son análisis
// distintos (`use_case` distinto en backend), así que comparten
// athleteId/recordId pero nunca query key ni caché de React Query.
const MEASUREMENT_QUERY_KEY = (
  athleteId: number,
  recordId: number,
  audience: PHVAudience,
) => ["ai", "measurement-explanation", athleteId, recordId, audience] as const;

/** Query GET /api/ai/athletes/{id}/measurements/{rid}/explanation — caché.
 *
 * Cada `recordId` tiene su propio slot de caché independiente, partido a su
 * vez por `audience`. Devuelve `null` cuando el backend responde 204 (sin
 * caché). `staleTime: Infinity` porque, una vez generada, la explicación es
 * inmutable hasta que el coach la regenere (lo cual invoca la mutation y
 * sobrescribe vía `setQueryData`).
 *
 * `audience` (default `"family"`, feature 042, T043): la variante `"coach"`
 * la pide la vista coach; el backend la rechaza con 403 para roles
 * distintos de coach/admin. */
export function useMeasurementExplanationCached(
  athleteId: number,
  recordId: number,
  enabled: boolean,
  audience: PHVAudience = "family",
) {
  return useQuery<AnthropometricRecordExplanationResponse | null>({
    queryKey: MEASUREMENT_QUERY_KEY(athleteId, recordId, audience),
    queryFn: () =>
      getMeasurementExplanationCached(athleteId, recordId, { audience }),
    enabled: enabled && athleteId > 0 && recordId > 0,
    staleTime: Infinity,
    retry: false,
  });
}

/** Mutation para POST /api/ai/athletes/{id}/measurements/{rid}/explanation.
 *
 * Sirve para "Analizar" la primera vez y "Regenerar". Tras éxito sincroniza
 * la queryKey individual del record (para la `audience` solicitada) vía
 * `setQueryData` para evitar GET extra.
 *
 * `audience` (default `"family"`, feature 042, T043): se reenvía tal cual a
 * `postMeasurementExplanation` y determina qué slot de caché
 * (`MEASUREMENT_QUERY_KEY`) se actualiza en éxito.
 *
 * Política de retry idéntica al PHV global: 503 hasta 2 reintentos con
 * backoff exponencial, 422/403/401/404/451/502 no reintentables. */
export function useMeasurementExplanation(
  athleteId: number,
  recordId: number,
  audience: PHVAudience = "family",
) {
  const queryClient = useQueryClient();

  return useMutation<
    AnthropometricRecordExplanationResponse,
    unknown,
    MeasurementExplanationVariables | void
  >({
    mutationKey: [
      "ai",
      "measurement-explanation",
      "generate",
      athleteId,
      recordId,
      audience,
    ],
    mutationFn: (vars) =>
      postMeasurementExplanation(athleteId, recordId, {
        signal: vars?.signal,
        audience,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(
        MEASUREMENT_QUERY_KEY(athleteId, recordId, audience),
        data,
      );
      // El resumen de crecimiento trae `latest_ai_analysis` (feature 042,
      // FR-027), que es lo que alimenta la línea de la pestaña Crecimiento.
      // Sin esta invalidación, el coach genera el análisis en el diálogo y la
      // línea sigue mostrando el anterior —o "sin análisis"— hasta que
      // remonte la pestaña. El servidor recalcula ahí también `is_stale`, así
      // que refetchear es la única forma correcta de actualizarla: ese dato
      // NO se deriva en el cliente.
      void queryClient.invalidateQueries({
        queryKey: ["growth-summary", athleteId],
      });
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
