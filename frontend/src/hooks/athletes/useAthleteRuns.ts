/**
 * Historial de runs del atleta (FE-1).
 *
 * RBAC: solo coach/admin. Los padres reciben 403, así que
 * deshabilitamos el query si el user actual es parent — evita un 403
 * espureo que ensucia los devtools de React Query.
 *
 * IMPORTANTE (params): el backend
 * (`backend/app/routers/athlete_race_analysis.py::list_athlete_runs`) sólo
 * declara `limit` y `offset`. `status` y `season` viajan en el tipo
 * `AthleteRunsParams` pero FastAPI los DESCARTA en silencio — no filtran
 * nada. Quien necesite filtrar por estado o temporada debe hacerlo en
 * cliente sobre `items` (ver `AthleteAIAnalysisTab.tsx`, recuperación de
 * runs activos).
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteRuns } from "@/api/athleteRaceAnalysis";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";
import type { AthleteRunsParams } from "@/types/athleteRaceAnalysis.types";

export interface UseAthleteRunsOptions {
  /**
   * Interruptor adicional del caller (se combina en AND con los chequeos
   * de sesión/rol). Sirve para vistas que renderizan en modo parent aunque
   * la sesión sea de coach/admin — el endpoint es coach-only, así que la
   * vista de padres nunca debe pedirlo.
   */
  enabled?: boolean;
}

export function useAthleteRuns(
  athleteId: number,
  params?: AthleteRunsParams,
  options?: UseAthleteRunsOptions,
) {
  const accessToken = useAuthStore((s) => s.accessToken);
  const role = useAuthStore((s) => s.user?.role);
  const isParent = role === UserRole.parent;
  return useQuery({
    queryKey: ["athlete-runs", athleteId, params ?? {}],
    queryFn: () => getAthleteRuns(athleteId, params),
    enabled:
      (options?.enabled ?? true) &&
      !!accessToken &&
      !isParent &&
      Number.isFinite(athleteId) &&
      athleteId > 0,
    staleTime: 15_000,
  });
}
