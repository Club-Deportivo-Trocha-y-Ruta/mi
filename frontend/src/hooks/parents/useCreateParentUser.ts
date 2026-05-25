import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createParentUser } from "@/api/parents";
import { parentKeys } from "@/api/queryKeys";

export function useCreateParentUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createParentUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: parentKeys.usersAll() });
    },
  });
}
