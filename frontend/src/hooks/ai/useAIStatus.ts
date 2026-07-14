import { useQuery } from "@tanstack/react-query";

import { getAIStatus } from "@/api/ai";

/** Query para GET /api/ai/status. Coach + admin.
 *
 * `staleTime` 30 s: presupuesto/concurrencia cambian a medida que otros
 * entrenadores lanzan análisis, así que se refresca con más frecuencia
 * que `useAIHealth` (2 min, casi estático).
 *
 * Diseñado para nunca bloquear el botón de lanzamiento que consume: en
 * caso de error de red, `isError` queda en `true` pero `data` es
 * `undefined` y los consumidores (`AnalyzeAthleteButton`,
 * `GroupAnalysisPanel`, etc.) deben degradar al comportamiento reactivo
 * de hoy (sin hint pre-lanzamiento, solo copy de 503/429 al fallar el
 * intento real) — `retry: false` para no demorar esa degradación.
 */
export function useAIStatus(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: ["ai-status"],
    queryFn: getAIStatus,
    staleTime: 30 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: false,
    enabled: options?.enabled ?? true,
  });
}
