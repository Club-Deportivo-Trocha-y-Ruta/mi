import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createAnthropometry, getAnthropometry } from "@/api/athletes";
import type { AnthropometryCreate } from "@/types/anthropometry.types";

export function useAnthropometry(athleteId: number) {
  return useQuery({
    queryKey: ["anthropometry", athleteId],
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
        queryKey: ["anthropometry", athleteId],
      });
      void queryClient.invalidateQueries({
        queryKey: ["athlete", athleteId],
      });
      // Feature 046 (T030): el resumen de crecimiento incluye el bloque de
      // composición corporal (banda, Σ4/Σ6, próxima fecha) — una nueva
      // medición antropométrica también puede cambiar `next_due_date`.
      void queryClient.invalidateQueries({
        queryKey: ["growth-summary", athleteId],
      });
      // Caché de explicación PHV se identifica por la última medición:
      // una nueva medición invalida la caché para que el coach vea el
      // botón "Generar" otra vez.
      void queryClient.invalidateQueries({
        queryKey: ["ai", "phv", athleteId],
      });
    },
  });
}
