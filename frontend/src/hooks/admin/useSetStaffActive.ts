import { useMutation, useQueryClient } from "@tanstack/react-query";

import { setUserActive } from "@/api/users";
import type { SetUserActivePayload } from "@/types/user.types";

/** contracts/staff-admin.md §4, §10 — desactivar/reactivar personal. */
export function useSetStaffActive() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, body }: { id: number; body: SetUserActivePayload }) =>
      setUserActive(id, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["staff"] });
    },
  });
}
