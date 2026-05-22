import { useQuery } from "@tanstack/react-query";

import { getMyAthletes } from "@/api/parents";
import { useAuthStore } from "@/store/auth.store";

/**
 * Privacy R2: el queryKey incluye `userId` para aislar el cache por
 * cuenta. Sin esto, dos padres usando la misma tablet podrían reusar
 * datos cacheados del otro. `enabled` también lo exige como defensa en
 * profundidad: si por algún motivo accessToken existe pero user es null,
 * la query no dispara con un key huérfano.
 */
export function useMyAthletes() {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useQuery({
    queryKey: ["my-athletes", userId],
    queryFn: getMyAthletes,
    enabled: !!accessToken && userId !== null,
  });
}
