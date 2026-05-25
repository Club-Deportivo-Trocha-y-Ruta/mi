/**
 * Historial de runs del atleta (FE-1).
 *
 * RBAC: solo coach/admin. Los padres reciben 403, así que
 * deshabilitamos el query si el user actual es parent — evita un 403
 * espureo que ensucia los devtools de React Query.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteRuns } from "@/api/athleteRaceAnalysis";
import { athleteKeys } from "@/api/queryKeys";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type { AthleteRunsParams } from "@/types/athleteRaceAnalysis.types";

export function useAthleteRuns(
  athleteId: number,
  params?: AthleteRunsParams,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const role = useAuthStore((s) => s.user?.role);
  const isParent = role === UserRole.parent;
  return useQuery({
    queryKey: athleteKeys.runs(athleteId, params),
    queryFn: () => getAthleteRuns(athleteId, params),
    enabled:
      !!accessToken &&
      !isParent &&
      Number.isFinite(athleteId) &&
      athleteId > 0,
    staleTime: 15_000,
  });
}
