/**
 * useCoachActivity — informe de actividad por entrenador de un club y
 * período (feature 041 — gobernanza multi-coach, US7). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §6.1.
 *
 * Convención de lista filtrada (`hooks/activities/useActivityReview.ts`):
 * `filters` entra completo en la queryKey para que cada combinación de
 * período/entrenador cachee por separado, y `keepPreviousData` evita el
 * parpadeo al cambiar de preset o de entrenador.
 *
 * La queryKey ("coach-activity") no se agrega a `PERSIST_ALLOWLIST_PREFIXES`
 * (`@/lib/persistAllowList` — default-deny): es una superficie interna de
 * gestión, nunca se persiste en el dispositivo (§4 del contrato).
 */
import { keepPreviousData, useQuery } from "@tanstack/react-query";

import { getCoachActivity } from "@/api/coachActivity";
import { useAuthStore } from "@/store/auth.store";
import type { CoachActivityParams } from "@/types/coachActivity.types";

export const coachActivityQueryKey = (
  clubId: number | undefined,
  filters: CoachActivityParams,
) => ["coach-activity", clubId ?? null, filters] as const;

export function useCoachActivity(
  clubId: number | undefined,
  filters: CoachActivityParams,
) {
  const accessToken = useAuthStore((s) => s.accessToken);

  return useQuery({
    queryKey: coachActivityQueryKey(clubId, filters),
    queryFn: ({ signal }) =>
      getCoachActivity(clubId as number, filters, { signal }),
    enabled: !!accessToken && !!clubId,
    placeholderData: keepPreviousData,
  });
}
