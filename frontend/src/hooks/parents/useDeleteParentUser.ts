import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteParentUser } from "@/api/parents";
import { parentKeys } from "@/api/queryKeys";

export function useDeleteParentUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => deleteParentUser(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: parentKeys.usersAll() });
      void queryClient.invalidateQueries({
        queryKey: parentKeys.athletesAll(),
      });
      void queryClient.invalidateQueries({ queryKey: ["parent", id] });
    },
  });
}
