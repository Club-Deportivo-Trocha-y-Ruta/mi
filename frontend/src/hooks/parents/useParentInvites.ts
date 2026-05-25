import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createParentInvite, getParentInvites } from "@/api/parents";
import { parentKeys } from "@/api/queryKeys";

export function useParentInvites(athleteId: number | undefined) {
  return useQuery({
    queryKey: parentKeys.invites(athleteId ?? 0),
    queryFn: () => getParentInvites(athleteId!),
    enabled: athleteId !== undefined && athleteId > 0,
  });
}

export function useCreateParentInvite() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createParentInvite,
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: parentKeys.invites(variables.athlete_id),
      });
    },
  });
}
