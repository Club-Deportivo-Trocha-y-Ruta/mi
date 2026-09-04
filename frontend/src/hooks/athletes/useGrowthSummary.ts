/**
 * useGrowthSummary — resumen de crecimiento derivado (feature 040, US2).
 *
 * Alimenta el tab de crecimiento decision-first del coach: etapa PHV,
 * velocidad, próxima medición, bandas del último registro y alertas — todo
 * calculado en el servidor sobre los dos registros más recientes
 * (`contracts/growth-summary-api.md`).
 *
 * Privacidad: la query key `["growth-summary", athleteId]` está
 * deliberadamente FUERA de `lib/persistAllowList.ts` (default-deny) — el
 * payload trae Z-scores/percentiles/bandas nutricionales de un menor y no
 * debe sobrevivir en el dispositivo entre sesiones.
 */
import { useQuery } from "@tanstack/react-query";

import { getGrowthSummary } from "@/api/growth";

export function useGrowthSummary(athleteId: number, enabled = true) {
  return useQuery({
    queryKey: ["growth-summary", athleteId],
    queryFn: () => getGrowthSummary(athleteId),
    enabled: enabled && Number.isFinite(athleteId) && athleteId > 0,
  });
}
