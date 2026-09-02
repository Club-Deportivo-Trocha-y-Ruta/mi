/**
 * Hook mutation para que el coach responda/califique un insight v3
 * (feature 037, T104/T205).
 *
 * POST /api/athletes/{id}/race-analysis/insights/{insight_id}/answer
 *
 * Actualización optimista: escribe `coach_answer_text`/`coach_rating` de
 * inmediato en la cache de detalle (`athlete-insight-detail`) y en el
 * item correspondiente de cualquier página de listado
 * (`athlete-insights`) cacheada, para que `CoachAnswerForm` refleje el
 * cambio sin esperar el roundtrip. Si la mutación falla, se revierte al
 * snapshot previo.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { answerInsight } from "@/api/athleteRaceAnalysis";
import type {
  AnswerInsightBody,
  AthleteInsightDetailOut,
  AthleteInsightListResponse,
} from "@/types/athleteRaceAnalysis.types";

interface AnswerInsightVars {
  insightId: number;
  body: AnswerInsightBody;
}

interface MutationContext {
  previousDetail: AthleteInsightDetailOut | undefined;
  previousLists: Array<[readonly unknown[], AthleteInsightListResponse]>;
}

export function useAnswerInsight(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation<AthleteInsightDetailOut, unknown, AnswerInsightVars, MutationContext>({
    mutationFn: ({ insightId, body }) => answerInsight(athleteId, insightId, body),
    onMutate: async ({ insightId, body }) => {
      const detailKey = ["athlete-insight-detail", athleteId, insightId];
      await queryClient.cancelQueries({ queryKey: detailKey });

      const previousDetail = queryClient.getQueryData<AthleteInsightDetailOut>(detailKey);

      const nowIso = new Date().toISOString();
      const patchInsight = <T extends { id: number }>(insight: T): T => {
        if (insight.id !== insightId) return insight;
        return {
          ...insight,
          ...(body.rating !== undefined ? { coach_rating: body.rating } : {}),
        };
      };

      if (previousDetail) {
        queryClient.setQueryData<AthleteInsightDetailOut>(detailKey, {
          ...patchInsight(previousDetail),
          ...(body.answer_text !== undefined
            ? { coach_answer_text: body.answer_text, coach_answer_at: nowIso }
            : {}),
        });
      }

      const previousLists = queryClient
        .getQueriesData<AthleteInsightListResponse>({
          queryKey: ["athlete-insights", athleteId],
        })
        .filter(
          (entry): entry is [readonly unknown[], AthleteInsightListResponse] =>
            entry[1] !== undefined,
        );
      for (const [key, data] of previousLists) {
        queryClient.setQueryData<AthleteInsightListResponse>(key, {
          ...data,
          items: data.items.map((item) => patchInsight(item)),
        });
      }

      return { previousDetail, previousLists };
    },
    onError: (_err, { insightId }, context) => {
      const detailKey = ["athlete-insight-detail", athleteId, insightId];
      if (context?.previousDetail) {
        queryClient.setQueryData(detailKey, context.previousDetail);
      }
      for (const [key, data] of context?.previousLists ?? []) {
        queryClient.setQueryData(key, data);
      }
    },
    onSuccess: (data, { insightId }) => {
      const detailKey = ["athlete-insight-detail", athleteId, insightId];
      queryClient.setQueryData(detailKey, data);
    },
    onSettled: (_data, _err, { insightId }) => {
      void queryClient.invalidateQueries({
        queryKey: ["athlete-insight-detail", athleteId, insightId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["athlete-insights", athleteId],
      });
    },
  });
}
