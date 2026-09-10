import { useMutation, useQueryClient } from "@tanstack/react-query";

import { deleteParentUser } from "@/api/parents";

export interface DeleteParentUserVars {
  id: number;
  /** Motivo del catálogo cerrado `ParentRemovalReasonCode` (auditoría, feature 041). */
  reasonCode: string;
}

export function useDeleteParentUser() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: ({ id, reasonCode }: DeleteParentUserVars) =>
      deleteParentUser(id, reasonCode),
    onSuccess: (_data, { id }) => {
      void queryClient.invalidateQueries({ queryKey: ["parent-users"] });
      void queryClient.invalidateQueries({ queryKey: ["parent-athletes"] });
      void queryClient.invalidateQueries({ queryKey: ["parent", id] });
    },
  });
}
