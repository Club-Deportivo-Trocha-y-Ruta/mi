import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteParentAthlete } from "@/api/parents";

export function useDeleteParentAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id }: { id: number; athlete_id: number; parent_id: number }) =>
      deleteParentAthlete(id),
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({ queryKey: ["parent-athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["parent-users"] });
      void queryClient.invalidateQueries({
        queryKey: ["athlete", variables.athlete_id],
      });
    },
  });
}
