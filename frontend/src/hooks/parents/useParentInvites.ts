import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { UseFormSetError } from "react-hook-form";

import { createParentInvite, getParentInvites } from "@/api/parents";
import { parentKeys } from "@/api/queryKeys";
import { applyPydanticErrors } from "@/lib/api/pydanticErrors";

export function useParentInvites(athleteId: number | undefined) {
  return useQuery({
    queryKey: parentKeys.invites(athleteId ?? 0),
    queryFn: () => getParentInvites(athleteId!),
    enabled: athleteId !== undefined && athleteId > 0,
  });
}

export function useCreateParentInvite<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createParentInvite,
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: (_data, variables) => {
      void queryClient.invalidateQueries({
        queryKey: parentKeys.invites(variables.athlete_id),
      });
    },
  });
}
