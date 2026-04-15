import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { createParentInvite, getParentInvites } from "@/api/parents";

export function useParentInvites(athleteId: number | undefined) {
  return useQuery({
    queryKey: ["parent-invites", athleteId],
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
        queryKey: ["parent-invites", variables.athlete_id],
      });
    },
  });
}
