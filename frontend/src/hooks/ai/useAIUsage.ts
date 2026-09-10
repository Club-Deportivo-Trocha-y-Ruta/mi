import { useQuery } from "@tanstack/react-query";

import { getAIUsage } from "@/api/raceAnalysis";

/**
 * Query para GET /api/race-analysis/admin/ai-usage. Coach + admin
 * (feature 041, gobernanza multi-coach, US6, §7.2 — RBAC ampliado desde
 * solo-admin).
 *
 * `staleTime` 2 min: el gasto acumulado de 30 días no cambia con
 * frecuencia suficiente como para justificar un refetch agresivo; el
 * coach puede reintentar manualmente vía `refetch()` si acaba de lanzar
 * un análisis y quiere ver el número actualizado.
 */
export function useAIUsage(options?: { days?: number; enabled?: boolean }) {
  const days = options?.days ?? 30;
  return useQuery({
    queryKey: ["race-analysis", "admin", "ai-usage", days],
    queryFn: ({ signal }) => getAIUsage({ days }, { signal }),
    staleTime: 2 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: false,
    enabled: options?.enabled ?? true,
  });
}
