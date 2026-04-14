import { useMutation, useQueryClient } from "@tanstack/react-query";

import { updateAthlete } from "@/api/athletes";
import type { AthleteUpdate } from "@/types/athlete.types";

interface UpdateAthleteInput {
  id: number;
  payload: AthleteUpdate;
}

export function useUpdateAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, payload }: UpdateAthleteInput) => updateAthlete(id, payload),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["athlete", variables.id] });
    },
  });
}
