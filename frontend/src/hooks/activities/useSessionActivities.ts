/**
 * Actividades Strava enlazadas a una sesión de entrenamiento (feature 025,
 * T033) — consumido por `SessionDetailPage` (FR-009).
 *
 * Mirror de `useAthleteActivities` — query simple habilitada solo con un
 * sessionId válido. RBAC (admin, coach del club, padre convocado) se aplica
 * en el backend; acá solo se consume la respuesta ya filtrada.
 */
import { useQuery } from "@tanstack/react-query";

import { getSessionActivities } from "@/api/stravaActivities";

export function useSessionActivities(sessionId: number, enabled = true) {
  return useQuery({
    queryKey: ["session-activities", sessionId],
    queryFn: ({ signal }) => getSessionActivities(sessionId, { signal }),
    enabled: enabled && Number.isFinite(sessionId) && sessionId > 0,
  });
}
