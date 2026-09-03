/**
 * useParentNewsletter — detalle de un boletín (bitácora) del padre
 * autenticado (feature 038). `stage_log` ya viene filtrado por
 * `to_parent_dto` en el backend.
 *
 * Privacy R2: userId al inicio del queryKey.
 */
import { useQuery } from "@tanstack/react-query";

import { getParentNewsletter } from "@/api/parentNewsletters";
import { useAuthStore } from "@/store/auth.store";

export function useParentNewsletter(
  athleteId: number | undefined,
  newsletterId: number | undefined,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const userId = useAuthStore((s) => s.user?.id ?? null);

  return useQuery({
    queryKey: ["parent-newsletter", userId, athleteId, newsletterId],
    queryFn: () => getParentNewsletter(athleteId!, newsletterId!),
    enabled: !!accessToken && !!athleteId && !!newsletterId,
  });
}
