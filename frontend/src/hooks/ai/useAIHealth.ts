import { useQuery } from "@tanstack/react-query";

import { getAIHealth } from "@/api/ai";
import { aiHealthKeys } from "@/api/queryKeys";

/** Query para GET /api/ai/health. Solo admin tiene acceso (403 para otros).
 *
 * `staleTime` 2 min: el estado del proveedor no cambia con frecuencia y no
 * queremos saturar al admin con refetches.
 */
export function useAIHealth(options?: { enabled?: boolean }) {
  return useQuery({
    queryKey: aiHealthKeys.health(),
    queryFn: getAIHealth,
    staleTime: 2 * 60 * 1000,
    gcTime: 5 * 60 * 1000,
    retry: false,
    enabled: options?.enabled ?? true,
  });
}
