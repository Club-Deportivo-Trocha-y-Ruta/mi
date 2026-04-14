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
    },
  });
}
