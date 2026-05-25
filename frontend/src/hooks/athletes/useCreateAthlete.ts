import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { UseFormSetError } from "react-hook-form";

import { createAthlete } from "@/api/athletes";
import { athleteKeys } from "@/api/queryKeys";
import { applyPydanticErrors } from "@/lib/api/pydanticErrors";

export function useCreateAthlete<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createAthlete,
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: athleteKeys.all });
    },
  });
}
