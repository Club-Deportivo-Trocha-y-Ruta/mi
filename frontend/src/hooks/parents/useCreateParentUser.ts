import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createParentUser } from "@/api/parents";

export function useCreateParentUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createParentUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["parent-users"] });
    },
  });
}
