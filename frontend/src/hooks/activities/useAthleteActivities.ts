/**
 * Listado paginado de actividades Strava de un atleta (feature 025, T024).
 *
 * Mirror de `useAthlete` — query simple habilitada solo con un athleteId
 * válido. RBAC (admin, coach del club, padre del propio hijo) se aplica en
 * el backend; acá solo se consume la respuesta ya filtrada.
 *
 * `params` (filtros linked/date_from/date_to/page/page_size) entra en la
 * queryKey para que cada combinación de filtros cachee por separado.
 */
import { useQuery } from "@tanstack/react-query";

import { getAthleteActivities } from "@/api/stravaActivities";
import type { ActivityListParams } from "@/types/strava.types";

export function useAthleteActivities(
  athleteId: number,
  params?: Omit<ActivityListParams, "athlete_id">,
  enabled = true,
) {
  return useQuery({
    queryKey: ["athlete-activities", athleteId, params ?? null],
    queryFn: ({ signal }) =>
      getAthleteActivities(athleteId, params, { signal }),
    enabled: enabled && Number.isFinite(athleteId) && athleteId > 0,
  });
}
