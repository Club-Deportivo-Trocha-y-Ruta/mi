/**
 * useParentNewsletters — lista de boletines (bitácora) enviados de un
 * atleta vinculado al padre autenticado (feature 038).
 *
 * Privacy R2: userId al inicio del queryKey (mismo patrón que
 * src/api/athleteNewsletters.ts y src/hooks/parents/useMyAthletes.ts).
 */
import { useQuery } from "@tanstack/react-query";

import { listParentNewsletters } from "@/api/parentNewsletters";
import { useAuthStore } from "@/store/auth.store";

export function useParentNewsletters(athleteId: number | undefined) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useQuery({
    queryKey: ["parent-newsletters", userId, athleteId],
    queryFn: () => listParentNewsletters(athleteId!),
    enabled: !!accessToken && !!athleteId,
  });
}
