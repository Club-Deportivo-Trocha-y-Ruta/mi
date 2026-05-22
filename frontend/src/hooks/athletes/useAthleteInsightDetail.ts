/**
 * Detalle de un insight aprobado/activo (FE-1).
 *
 * Solo se dispara cuando ``insightId`` está definido (lazy-load para
 * el modal/sheet de detalle). El backend devuelve 404 para padres si
 * la fila no es activa+aprobada — TanStack Query expone ese error
 * pero no debería verse en mode=parent porque la lista que abrió el
 * detalle ya está filtrada.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteInsight } from "@/api/athleteRaceAnalysis";
import { useAuthStore } from "@/store/auth.store";

export function useAthleteInsightDetail(
  athleteId: number,
  insightId: number | null | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  return useQuery({
    queryKey: ["athlete-insight-detail", athleteId, insightId],
    queryFn: () => {
      if (!insightId) throw new Error("insightId requerido");
      return getAthleteInsight(athleteId, insightId);
    },
    enabled:
      !!accessToken &&
      Number.isFinite(athleteId) &&
      athleteId > 0 &&
      !!insightId &&
      insightId > 0,
    staleTime: 60_000,
  });
}
