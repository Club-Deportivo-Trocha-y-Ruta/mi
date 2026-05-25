import { useMutation, useQueryClient } from "@tanstack/react-query";
import type { UseFormSetError } from "react-hook-form";

import { createParentUser } from "@/api/parents";
import { parentKeys } from "@/api/queryKeys";
import { applyPydanticErrors } from "@/lib/api/pydanticErrors";

export function useCreateParentUser<
  T extends Record<string, unknown> = Record<string, unknown>,
>(options?: { setError?: UseFormSetError<T> }) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: createParentUser,
    onError: (err) => {
      if (options?.setError) {
        applyPydanticErrors<T>(err, options.setError);
      }
    },
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: parentKeys.usersAll() });
    },
  });
}
