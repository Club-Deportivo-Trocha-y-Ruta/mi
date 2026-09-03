/**
 * useRegenerateBlock — regenera un bloque puntual de la bitácora con IA
 * (feature 038, `POST /{id}/regenerate-block`).
 *
 * Privacy R2: invalida por queryKey completo ["athlete-newsletter", userId, ...]
 * y ["athlete-newsletters", userId, ...], igual que el resto de mutaciones en
 * `src/api/athleteNewsletters.ts`.
 */
import { useMutation, useQueryClient } from "@tanstack/react-query";

import { regenerateNewsletterBlock } from "@/api/athleteNewsletters";
import { useAuthStore } from "@/store/auth.store";
import type { RegenerateBlockRequest } from "@/types/athleteNewsletter.types";

export function useRegenerateBlock(athleteId: number, newsletterId: number) {
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useMutation({
    mutationFn: (body: RegenerateBlockRequest) =>
      regenerateNewsletterBlock(athleteId, newsletterId, body),
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
