import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createAnthropometry, getAnthropometry } from "@/api/athletes";
import { anthropometryKeys, athleteKeys } from "@/api/queryKeys";
import type { AnthropometryCreate } from "@/types/anthropometry.types";

export function useAnthropometry(athleteId: number) {
  return useQuery({
    queryKey: anthropometryKeys.list(athleteId),
    queryFn: () => getAnthropometry(athleteId),
    enabled: athleteId > 0,
  });
}

export function useCreateAnthropometry(athleteId: number) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AnthropometryCreate) =>
      createAnthropometry(athleteId, payload),
    onSuccess: () => {
      void queryClient.invalidateQueries({
        queryKey: anthropometryKeys.list(athleteId),
      });
      void queryClient.invalidateQueries({
        queryKey: athleteKeys.detail(athleteId),
      });
      // Caché de explicación PHV se identifica por la última medición:
      // una nueva medición invalida la caché para que el coach vea el
      // botón "Generar" otra vez.
      void queryClient.invalidateQueries({
        queryKey: anthropometryKeys.aiPhv(athleteId),
      });
    },
  });
}
