/**
 * Listado de insights aprobados/activos del atleta (FE-1).
 *
 * El backend ya filtra por rol — un padre verá únicamente
 * ``coach_approved=true`` y ``is_active=true``. El frontend no debe
 * intentar enviar ``include_deprecated=true`` para parents (el backend
 * lo ignora pero igual el flag se queda en el cache key, lo que
 * podría generar misses inútiles).
 *
 * staleTime: 30s — los insights aprobados cambian raramente, pero
 * tras un HITL approve el coach quiere ver el nuevo casi inmediato.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteInsights } from "@/api/athleteRaceAnalysis";
import { athleteKeys } from "@/api/queryKeys";
import { useAuthStore } from "@/store/auth.store";
import type { AthleteInsightsParams } from "@/types/athleteRaceAnalysis.types";

export function useAthleteInsights(
  athleteId: number,
  params?: AthleteInsightsParams,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: athleteKeys.insights(athleteId, params),
    queryFn: () => getAthleteInsights(athleteId, params),
    enabled: !!accessToken && Number.isFinite(athleteId) && athleteId > 0,
    staleTime: 30_000,
  });
}
