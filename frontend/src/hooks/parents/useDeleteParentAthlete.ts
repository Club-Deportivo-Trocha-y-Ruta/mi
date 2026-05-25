import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteParentAthlete } from "@/api/parents";
import { athleteKeys, parentKeys } from "@/api/queryKeys";

export function useDeleteParentAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id }: { id: number; athlete_id: number; parent_id: number }) =>
      deleteParentAthlete(id),
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
