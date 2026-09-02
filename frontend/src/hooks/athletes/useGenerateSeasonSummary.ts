/**
 * Hook mutation para lanzar el resumen de temporada on-demand (feature
 * 037, T205 — contrato v3 asíncrono).
 *
 * POST /api/athletes/{id}/race-analysis/season-summary
 *
 * Devuelve `{run_id, status}` (ver `AthleteSeasonSummaryRunResponse`) —
 * el resumen se genera en background como cualquier run agéntico. Quien
 * monte este hook debe seguir el `run_id` con `getRunStatus`/
 * `useRunStatus` (`api/raceAnalysis.ts`) hasta un estado terminal antes
 * de esperar ver el insight nuevo en `getAthleteInsights`.
 *
 * En onSuccess invalida todas las queries "athlete-*" del atleta para que
 * el header y el histórico de InsightsTimeline reflejen el run recién
 * lanzado (aparece en `useAthleteRuns`).
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
