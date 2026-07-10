/**
 * Listado paginado de actividades Strava para la vista de revisión del
 * coach/admin (feature 025, T031) — consumido por `ActivityReviewPage`
 * (FR-010).
 *
 * Mirror de `useAthleteActivities` — query simple, habilitada siempre (el
 * scoping por club/rol lo aplica el backend en `GET /api/activities`; acá
 * solo se consume la respuesta ya filtrada). `params` entra completo en la
 * queryKey para que cada combinación de filtros (linked/athlete_id/rango de
 * fechas/página) cachee por separado.
 *
 * La mutation de enlace (`useLinkActivity`, T032) invalida la queryKey base
 * `["activities-review"]` para refrescar esta lista tras enlazar/desenlazar.
 *
 * `useSessionSuggestions` — GET /api/activities/{id}/session-suggestions
 * (FR-008), sesiones candidatas para vincular una actividad puntual.
 * Consumido por `LinkSessionDialog` (T032) para la lista de radios
 * principal (mismo día + asistencia primero, ordenado por el backend).
 */
import { useQuery } from "@tanstack/react-query";

import { getActivities, getSessionSuggestions } from "@/api/stravaActivities";
import type { ActivityListParams } from "@/types/strava.types";

export const activityReviewQueryKey = (params?: ActivityListParams) =>
  ["activities-review", params ?? null] as const;

export function useActivityReview(params?: ActivityListParams, enabled = true) {
  return useQuery({
    queryKey: activityReviewQueryKey(params),
    queryFn: ({ signal }) => getActivities(params, { signal }),
    enabled,
  });
}

export function useSessionSuggestions(activityId: number, enabled = true) {
  return useQuery({
    queryKey: ["activity-session-suggestions", activityId],
    queryFn: ({ signal }) => getSessionSuggestions(activityId, { signal }),
    enabled: enabled && Number.isFinite(activityId) && activityId > 0,
  });
}
