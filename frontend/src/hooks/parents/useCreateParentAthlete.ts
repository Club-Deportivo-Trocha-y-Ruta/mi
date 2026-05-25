import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createParentAthlete } from "@/api/parents";
import { athleteKeys, parentKeys } from "@/api/queryKeys";

export function useCreateParentAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createParentAthlete,
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: parentKeys.athletesAll(),
      });
      void queryClient.invalidateQueries({ queryKey: parentKeys.usersAll() });
      void queryClient.invalidateQueries({
        queryKey: athleteKeys.detail(variables.athlete_id),
      });
    },
  });
}
