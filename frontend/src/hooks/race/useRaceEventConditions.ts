/**
 * Hooks TanStack Query del módulo race-events — condiciones de carrera (F-COND).
 *
 * - `useUpdateRaceEventConditions()` → mutation PATCH /race-events/{id}/conditions.
 *   Invalida `["race-analysis"]` al éxito para refrescar analíticas que
 *   muestran las condiciones del evento (runs/status, runs/result, etc.).
 *
 * El toast de éxito/error vive en el componente que consume este hook
 * (patrón establecido en UnlinkedCompetitorsTab — banner sin librería externa).
 */
import {
  useMutation,
  useQueryClient,
} from "@tanstack/react-query";

import { updateRaceEventConditions } from "@/api/raceEvents";
import type {
  RaceEventConditions,
  RaceEventConditionsUpdate,
} from "@/types/raceEvents.types";

// ---------------------------------------------------------------------------
// Query keys del módulo race-analysis (mismas raíces que useRaceRun.ts)
// ---------------------------------------------------------------------------

/**
 * Raíz del árbol de queries de análisis de carreras.
 * Invalidar con este prefijo refresca status, result y cualquier sublista.
 * Mantener sincronizado con `raceRunKeys.all` en `hooks/ai/useRaceRun.ts`.
 */
const RACE_ANALYSIS_ROOT = ["race-analysis"] as const;

// ---------------------------------------------------------------------------
// Variables de la mutation
// ---------------------------------------------------------------------------

export interface UseUpdateRaceEventConditionsVariables {
  /** ID del evento a actualizar. */
  raceEventId: number;
  /** Campos de condición a modificar (todos opcionales — merge semántico). */
  body: RaceEventConditionsUpdate;
}

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

/**
 * Mutation para actualizar las condiciones logísticas de un evento de carrera.
 *
 * Uso en componente:
 * ```tsx
 * const { mutate, isPending } = useUpdateRaceEventConditions();
 *
 * mutate(
 *   { raceEventId: 42, body: { surface_condition: "barro", temperature_c: 18 } },
 *   {
 *     onSuccess: (data) => mostrarToast("Condiciones guardadas"),
 *     onError: (err) => mostrarToast("Error al guardar", "error"),
 *   },
 * );
 * ```
 *
 * Las callbacks `onSuccess`/`onError` se pasan en el sitio de llamada
 * para que el componente controle el toast según su contexto de UI.
 * La invalidación de queries siempre ocurre (definida aquí, no en el caller).
 */
export function useUpdateRaceEventConditions() {
  const queryClient = useQueryClient();

  return useMutation<
    RaceEventConditions,
    unknown,
    UseUpdateRaceEventConditionsVariables
  >({
    mutationKey: ["race-events", "update-conditions"],
    mutationFn: ({ raceEventId, body }) =>
      updateRaceEventConditions(raceEventId, body),
    onSuccess: (_data, variables) => {
      // Invalida todo el árbol de análisis de carreras para que el resultado
      // del run refleje las nuevas condiciones del evento.
      void queryClient.invalidateQueries({
        queryKey: RACE_ANALYSIS_ROOT,
      });
      // Invalida también la clave específica por evento si existiera en caché
      // (preparación para queries futuras que traigan el race_event por id).
      void queryClient.invalidateQueries({
        queryKey: ["race-events", variables.raceEventId],
      });
    },
  });
}
