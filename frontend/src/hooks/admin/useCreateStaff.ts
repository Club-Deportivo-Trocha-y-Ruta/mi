import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createStaffUser } from "@/api/users";

/** contracts/staff-admin.md §9 — creación de personal (coach/admin). */
export function useCreateStaff() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createStaffUser,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["staff"] });
    },
  });
}
