/**
 * useBodyComposition — detalle de composición corporal por pliegues
 * (feature 046, US2), coach/admin únicamente.
 *
 * Alimenta tanto `BodyCompositionCard` (Σ4/Σ6, sparkline, cambio, próxima
 * toma) como `BodyCompositionDetailDialog` (series por sitio, sets crudos,
 * referencia FUPRECOL) desde `GrowthTab.tsx` (T040) — una sola query
 * `GET .../body-composition`, compartida por ambos vía la misma
 * `UseQueryResult`, en vez de que cada componente dispare la suya. El
 * bloque `body_composition` embebido en `useGrowthSummary` es un resumen
 * aparte (para el boletín/las tarjetas de familia), no la fuente de este
 * hook. El backend responde 403 a un padre; este hook nunca se habilita
 * fuera del coach/admin — pasar `enabled=false` desde el llamador para el
 * rol `parent`.
 *
 * Privacidad: la query key `["body-composition", athleteId]` está
 * deliberadamente FUERA de `lib/persistAllowList.ts` (default-deny) — el
 * payload trae pliegues/estimaciones de un menor y no debe sobrevivir en el
 * dispositivo entre sesiones (mismo criterio que `useGrowthSummary`).
 */
import { useMutation, useQuery, useQueryClient, type QueryClient } from "@tanstack/react-query";

import { deleteSkinfolds, getBodyComposition, saveSkinfolds } from "@/api/bodyComposition";
import type { SkinfoldSetIn } from "@/types/bodyComposition.types";

export function useBodyComposition(athleteId: number, enabled = true) {
  return useQuery({
    queryKey: ["body-composition", athleteId],
    queryFn: () => getBodyComposition(athleteId),
    enabled: enabled && Number.isFinite(athleteId) && athleteId > 0,
  });
}

/**
 * Invalida todo lo que depende de un set de pliegues
 * (`contracts/skinfolds-api.md` §8): detalle de composición, historial
 * antropométrico (`skinfolds` por fila), resumen de crecimiento (bloque
 * `body_composition`) y la caché de explicación PHV.
 */
function invalidateSkinfoldDependents(queryClient: QueryClient, athleteId: number) {
  void queryClient.invalidateQueries({ queryKey: ["body-composition", athleteId] });
  void queryClient.invalidateQueries({ queryKey: ["anthropometry", athleteId] });
  void queryClient.invalidateQueries({ queryKey: ["growth-summary", athleteId] });
  void queryClient.invalidateQueries({ queryKey: ["ai", "phv", athleteId] });
}

/** PUT del set de pliegues de una evaluación (crea o reemplaza). */
export function useSaveSkinfolds(athleteId: number, recordId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: SkinfoldSetIn) => saveSkinfolds(athleteId, recordId, payload),
    onSuccess: () => invalidateSkinfoldDependents(queryClient, athleteId),
  });
}

/** DELETE del set de pliegues de una evaluación. */
export function useDeleteSkinfolds(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (recordId: number) => deleteSkinfolds(athleteId, recordId),
    onSuccess: () => invalidateSkinfoldDependents(queryClient, athleteId),
  });
}
