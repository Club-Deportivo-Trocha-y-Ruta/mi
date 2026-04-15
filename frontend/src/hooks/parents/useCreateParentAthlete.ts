import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createParentAthlete } from "@/api/parents";

export function useCreateParentAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createParentAthlete,
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["parent-athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["parent-users"] });
      void queryClient.invalidateQueries({
        queryKey: ["athlete", variables.athlete_id],
      });
    },
  });
}
