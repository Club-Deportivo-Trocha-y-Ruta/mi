/**
 * Mutation para lanzar un análisis del atleta (FE-1).
 *
 * En onSuccess invalida las queries del listado de runs e insights
 * para que la UI re-fetchee y muestre el nuevo run. La predicate
 * matchea el athleteId (segundo elemento del queryKey), así otros
 * atletas no son afectados.
 *
 * Además invalida ``club-insights-by-race`` (grid cross-atleta del tab
 * Insights / freshness de ResultsTable): no está keyado por athleteId, así
 * que se invalida completa para reflejar el nuevo run cuando complete.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { startAthleteRun } from "@/api/athleteRaceAnalysis";
import type {
  AthleteStartRunBody,
  AthleteRunOut,
} from "@/types/athleteRaceAnalysis.types";

export function useLaunchAthleteAnalysis(athleteId: number) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationKey: ["launch-athlete-analysis", athleteId],
    mutationFn: (body: AthleteStartRunBody) =>
      startAthleteRun(athleteId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        predicate: (q) => {
          const key = q.queryKey;
          if (!Array.isArray(key)) return false;
          const [base, id] = key;
          // Grid cross-atleta: no keyado por athleteId → invalidar siempre.
          if (base === "club-insights-by-race") return true;
          return (
            (base === "athlete-runs" || base === "athlete-insights") &&
            id === athleteId
          );
        },
      });
    },
  });
}

/** Re-export para que el componente caller pueda tipar la respuesta. */
export type { AthleteRunOut };
