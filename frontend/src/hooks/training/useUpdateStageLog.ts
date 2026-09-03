/**
 * useUpdateStageLog — envuelve el PATCH existente de
 * `usePatchNewsletter`/`patchAthleteNewsletter` para los campos nuevos de
 * la bitácora (`stage_overrides`, `hidden_blocks`, `coach_note`,
 * `selected_race_insight_ids`), feature 038.
 *
 * Se mantiene como hook independiente (en vez de reusar directamente
 * `usePatchNewsletter`) porque el estudio necesita un payload con nombre
 * explícito para el flujo de PATCH-on-blur descrito en data-model.md §6.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { patchAthleteNewsletter } from "@/api/athleteNewsletters";
import { useAuthStore } from "@/store/auth.store";
import type {
  HideableBlock,
  StageOverrides,
} from "@/types/stageLog.types";

export interface UpdateStageLogPayload {
  stage_overrides?: StageOverrides;
  hidden_blocks?: HideableBlock[];
  coach_note?: string | null;
  selected_race_insight_ids?: number[];
}

export function useUpdateStageLog(athleteId: number, newsletterId: number) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useMutation({
    mutationFn: (payload: UpdateStageLogPayload) =>
      patchAthleteNewsletter(athleteId, newsletterId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: ["athlete-newsletter", userId, athleteId, newsletterId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["athlete-newsletters", userId, athleteId],
      });
    },
  });
}
