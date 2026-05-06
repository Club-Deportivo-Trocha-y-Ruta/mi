import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteParentUser } from "@/api/parents";

export function useDeleteParentUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: (id: number) => deleteParentUser(id),
    onSuccess: (_data, id) => {
      void queryClient.invalidateQueries({ queryKey: ["parent-users"] });
      void queryClient.invalidateQueries({ queryKey: ["parent-athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["parent", id] });
    },
  });
}
