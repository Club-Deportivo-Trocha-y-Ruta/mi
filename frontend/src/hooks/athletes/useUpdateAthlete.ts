import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { UseFormSetError } from "react-hook-form";

import { updateAthlete } from "@/api/athletes";
import { athleteKeys } from "@/api/queryKeys";
import { applyPydanticErrors } from "@/lib/api/pydanticErrors";
import type { AthleteUpdate } from "@/types/athlete.types";

interface UpdateAthleteInput {
  id: number;
  payload: AthleteUpdate;
}

export function useUpdateAthlete<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: UpdateAthleteInput) => updateAthlete(id, payload),
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: athleteKeys.all });
      void queryClient.invalidateQueries({
        queryKey: athleteKeys.detail(variables.id),
      });
    },
  });
}
