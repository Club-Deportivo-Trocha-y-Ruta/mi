/**
 * useUpdateStageLog — envuelve el PATCH existente de
 * `usePatchNewsletter`/`patchAthleteNewsletter` para los campos nuevos de
 * la bitácora (`stage_overrides`, `hidden_blocks`, `coach_note`,
 * `selected_race_insight_ids`), feature 038.
 *
 * Se mantiene como hook independiente (en vez de reusar directamente
 * `usePatchNewsletter`) porque el estudio necesita un payload con nombre
 * explícito para el flujo de PATCH-on-blur descrito en data-model.md §6.
 *
 * Concurrencia optimista (041 §2, T073): `expectedVersion` es OBLIGATORIA
 * — el backend responde 428 sin ella. El estudio la toma siempre de
 * `newsletter.edit_version` ya cargado (nunca inventada en el cliente).
 */
import { isAxiosError } from "axios";
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
  /** Versión cargada del boletín (`newsletter.edit_version`) — precondición 041 §2.2. */
  expectedVersion: number;
}

export function useUpdateStageLog(athleteId: number, newsletterId: number) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useMutation({
    mutationFn: ({ expectedVersion, ...payload }: UpdateStageLogPayload) =>
      patchAthleteNewsletter(athleteId, newsletterId, {
        ...payload,
        expected_version: expectedVersion,
      }),
    // 041 §6.1 (R-16): 400 (precondición inválida), 409 (versión vencida o
    // boletín en estado terminal) y 428 (falta la precondición) son
    // respuestas correctas y estables del backend — reintentar repite
    // exactamente el mismo error para siempre, porque la versión cargada
    // en el cliente no cambia sola. Cualquier otro fallo (red, 500) sí
    // puede beneficiarse de un reintento.
    retry: (_failureCount, error) => {
      const status = isAxiosError(error) ? error.response?.status : undefined;
      return status === undefined || ![400, 409, 428].includes(status);
    },
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
