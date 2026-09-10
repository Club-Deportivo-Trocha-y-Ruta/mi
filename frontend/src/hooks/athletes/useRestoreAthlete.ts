import { useMutation, useQueryClient } from "@tanstack/react-query";

import { restoreAthlete } from "@/api/athletes";

/** contracts/athlete-archive.md §2 — admin only. */
export function useRestoreAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reasonCode }: { id: number; reasonCode: string }) =>
      restoreAthlete(id, reasonCode),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: ["athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["athlete", id] });
      void queryClient.invalidateQueries({ queryKey: ["parent-athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
}
