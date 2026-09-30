import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  checkPlausibility,
  createAnthropometry,
  deleteAnthropometry,
  getAnthropometry,
  getAnthropometryRoster,
  updateAnthropometry,
} from "@/api/athletes";
import type {
  AnthropometryCreate,
  AnthropometryUpdate,
  PlausibilityCheckRequest,
} from "@/types/anthropometry.types";

export function useAnthropometry(athleteId: number) {
  return useQuery({
    queryKey: ["anthropometry", athleteId],
    queryFn: () => getAnthropometry(athleteId),
    enabled: athleteId > 0,
  });
}

/** Prefijo de la query del roster de la jornada grupal (feature 048, T043). */
export const ANTHROPOMETRY_ROSTER_KEY = "anthropometry-roster";

/**
 * Roster de la jornada de medición (`GET /api/anthropometry/roster`): última
 * evaluación, «Medido hoy» y elegibilidad de pliegues por deportista en
 * `date` (YYYY-MM-DD). Se invalida con cualquier alta, edición o borrado.
 */
export function useAnthropometryRoster(date: string, enabled = true) {
  return useQuery({
    queryKey: [ANTHROPOMETRY_ROSTER_KEY, date],
    queryFn: () => getAnthropometryRoster(date),
    enabled: enabled && date.length > 0,
  });
}

export function useCreateAnthropometry(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AnthropometryCreate) =>
      createAnthropometry(athleteId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["anthropometry", athleteId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["athlete", athleteId],
      });
      // Feature 046 (T030): el resumen de crecimiento incluye el bloque de
      // composición corporal (banda, Σ4/Σ6, próxima fecha) — una nueva
      // medición antropométrica también puede cambiar `next_due_date`.
      void queryClient.invalidateQueries({
        queryKey: ["growth-summary", athleteId],
      });
      // Caché de explicación PHV se identifica por la última medición:
      // una nueva medición invalida la caché para que el coach vea el
      // botón "Generar" otra vez.
      void queryClient.invalidateQueries({
        queryKey: ["ai", "phv", athleteId],
      });
      // Feature 048 (T043): «Medido hoy» y la última evaluación del roster.
      void queryClient.invalidateQueries({
        queryKey: [ANTHROPOMETRY_ROSTER_KEY],
      });
    },
  });
}

/**
 * Invalida todo lo derivado de una medición (feature 048): historial,
 * ficha, resumen de crecimiento, explicación PHV, composición corporal
 * (los pliegues cuelgan de la evaluación) y explicaciones IA por registro.
 */
function invalidateAnthropometryDerived(
  queryClient: ReturnType<typeof useQueryClient>,
  athleteId: number,
) {
  const keys: readonly (readonly unknown[])[] = [
    ["anthropometry", athleteId],
    ["athlete", athleteId],
    ["growth-summary", athleteId],
    ["ai", "phv", athleteId],
    ["body-composition", athleteId],
    ["ai", "measurement-explanation", athleteId],
    [ANTHROPOMETRY_ROSTER_KEY],
  ];
  for (const queryKey of keys) {
    void queryClient.invalidateQueries({ queryKey });
  }
}

export function useUpdateAnthropometry(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({
      recordId,
      payload,
    }: {
      recordId: number;
      payload: AnthropometryUpdate;
    }) => updateAnthropometry(athleteId, recordId, payload),
    onSuccess: () => invalidateAnthropometryDerived(queryClient, athleteId),
  });
}

export function useDeleteAnthropometry(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (recordId: number) => deleteAnthropometry(athleteId, recordId),
    onSuccess: () => invalidateAnthropometryDerived(queryClient, athleteId),
  });
}

/** Dry-run de plausibilidad (feature 048): mutation sin caché, no escribe nada. */
export function usePlausibilityCheck(athleteId: number) {
  return useMutation({
    mutationFn: (payload: PlausibilityCheckRequest) =>
      checkPlausibility(athleteId, payload),
  });
}
