import { useMutation, useQueryClient } from "@tanstack/react-query";

import { archiveAthlete } from "@/api/athletes";

/**
 * Reemplaza useDeleteAthlete (feature 041 — el DELETE ahora archiva en vez
 * de borrar). contracts/athlete-archive.md §1.
 */
export function useArchiveAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reasonCode }: { id: number; reasonCode: string }) =>
      archiveAthlete(id, reasonCode),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: ["athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["athlete", id] });
      void queryClient.invalidateQueries({ queryKey: ["parent-athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-stats"] });
      void queryClient.invalidateQueries({ queryKey: ["dashboard-summary"] });
    },
  });
}
