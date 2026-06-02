/**
 * Hook TanStack Query para el panorama de temporada (PR3 unificación
 * /competitions). Alimenta `/competitions/insights/season/:year`.
 *
 * RBAC aplicado en backend: coach/admin (parents → 403). El hook queda
 * deshabilitado si `year` no es un número válido.
 *
 * Privacidad: el query key incluye `year` y `clubId`, ambos no-PII.
 */
import { useQuery } from "@tanstack/react-query";

import { getSeasonPanorama } from "@/api/athleteRaceAnalysis";

export function useSeasonPanorama(year: number | null, clubId?: number) {
  return useQuery({
    queryKey: ["season-panorama", year, clubId],
    queryFn: () => getSeasonPanorama(year!, clubId),
    enabled: year !== null && !Number.isNaN(year),
    staleTime: 60_000,
  });
}
