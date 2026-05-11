import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  getMeasurementExplanationCached,
  mapAIError,
  postMeasurementExplanation,
} from "@/api/ai";
import type { AnthropometricRecordExplanationResponse } from "@/types/ai.types";

interface MeasurementExplanationVariables {
  signal?: AbortSignal;
}

const MEASUREMENT_QUERY_KEY = (athleteId: number, recordId: number) =>
  ["ai", "measurement-explanation", athleteId, recordId] as const;

/** Query GET /api/ai/athletes/{id}/measurements/{rid}/explanation — caché.
 *
 * Cada `recordId` tiene su propio slot de caché independiente. Devuelve
 * `null` cuando el backend responde 204 (sin caché). `staleTime: Infinity`
 * porque, una vez generada, la explicación es inmutable hasta que el coach
 * la regenere (lo cual invoca la mutation y sobrescribe vía `setQueryData`). */
export function useMeasurementExplanationCached(
  athleteId: number,
  recordId: number,
  enabled: boolean,
) {
  return useQuery<AnthropometricRecordExplanationResponse | null>({
    queryKey: MEASUREMENT_QUERY_KEY(athleteId, recordId),
    queryFn: () => getMeasurementExplanationCached(athleteId, recordId),
    enabled: enabled && athleteId > 0 && recordId > 0,
    staleTime: Infinity,
    retry: false,
  });
}

/** Mutation para POST /api/ai/athletes/{id}/measurements/{rid}/explanation.
 *
 * Sirve para "Analizar" la primera vez y "Regenerar". Tras éxito sincroniza
 * la queryKey individual del record vía `setQueryData` para evitar GET extra.
 *
 * Política de retry idéntica al PHV global: 503 hasta 2 reintentos con
 * backoff exponencial, 422/403/401/404/451/502 no reintentables. */
export function useMeasurementExplanation(
  athleteId: number,
  recordId: number,
) {
  const queryClient = useQueryClient();

  return useMutation<
    AnthropometricRecordExplanationResponse,
    unknown,
    MeasurementExplanationVariables | void
  >({
    mutationKey: ["ai", "measurement-explanation", "generate", athleteId, recordId],
    mutationFn: (vars) =>
      postMeasurementExplanation(athleteId, recordId, {
        signal: vars?.signal,
      }),
    onSuccess: (data) => {
      queryClient.setQueryData(
        MEASUREMENT_QUERY_KEY(athleteId, recordId),
        data,
      );
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
