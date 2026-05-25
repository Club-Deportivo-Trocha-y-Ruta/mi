import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseFormSetError } from "react-hook-form";

import { createAnthropometry, getAnthropometry } from "@/api/athletes";
import { anthropometryKeys, athleteKeys } from "@/api/queryKeys";
import { applyPydanticErrors } from "@/lib/api/pydanticErrors";
import type { AnthropometryCreate } from "@/types/anthropometry.types";

export function useAnthropometry(athleteId: number) {
  return useQuery({
    queryKey: anthropometryKeys.list(athleteId),
    queryFn: () => getAnthropometry(athleteId),
    enabled: athleteId > 0,
  });
}

export function useCreateAnthropometry<
  T extends Record<string, unknown> = Record<string, unknown>,
>(athleteId: number, options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (payload: AnthropometryCreate) =>
      createAnthropometry(athleteId, payload),
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
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
