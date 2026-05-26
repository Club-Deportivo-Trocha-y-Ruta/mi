/**
 * Hook mutation para generar el resumen de temporada on-demand (Task #8).
 *
 * POST /api/athletes/{id}/race-analysis/season-summary
 *
 * En onSuccess invalida todas las queries "athlete-*" del atleta para que
 * el header y el histórico de InsightsTimeline reflejen el nuevo run.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { generateSeasonSummary } from "@/api/athleteRaceAnalysis";

export function useGenerateSeasonSummary(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: () => generateSeasonSummary(athleteId),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        predicate: (q) => {
          const k = q.queryKey;
          return (
            Array.isArray(k) &&
            typeof k[0] === "string" &&
            (k[0] as string).startsWith("athlete-")
          );
        },
      });
    },
  });
}
