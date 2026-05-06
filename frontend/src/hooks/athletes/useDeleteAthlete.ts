import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteAthlete } from "@/api/athletes";

export function useDeleteAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => deleteAthlete(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ["athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["athlete", id] });
      void queryClient.invalidateQueries({ queryKey: ["parent-athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
    },
  });
}
