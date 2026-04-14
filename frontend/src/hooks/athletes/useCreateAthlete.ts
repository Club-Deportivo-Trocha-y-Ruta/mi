import { useMutation, useQueryClient } from "@tanstack/react-query";

import { createAthlete } from "@/api/athletes";

export function useCreateAthlete() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: createAthlete,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["athletes"] });
    },
  });
}
