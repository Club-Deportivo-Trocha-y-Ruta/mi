import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteAthlete } from "@/api/athletes";
import { athleteKeys, parentKeys } from "@/api/queryKeys";

export function useDeleteAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => deleteAthlete(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: athleteKeys.all });
      void queryClient.invalidateQueries({ queryKey: athleteKeys.detail(id) });
      void queryClient.invalidateQueries({ queryKey: parentKeys.athletesAll() });
      void queryClient.invalidateQueries({
        queryKey: athleteKeys.dashboardStats(),
      });
    },
  });
}
