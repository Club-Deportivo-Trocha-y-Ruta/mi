/**
 * useUnlinkedActivitiesNearDate — actividades Strava sin enlazar cerca de
 * la fecha de una sesión (specs/025-strava-activity-sync/session-detail-redesign.md
 * §3.4). Alimenta el estado "sin enlazar" de `ActivityEvidenceStrip` en
 * `SessionDetailPage` para que el coach pueda enlazar manualmente sin salir
 * a la página de Revisión de actividades.
 *
 * Reutiliza `GET /api/activities` (misma RBAC coach/admin del resto del
 * módulo Strava — 403 para parent/athlete ya aplicado en el backend, así
 * que no hace falta un gate adicional acá).
 *
 * Ventana ±1 día: espeja la ventana de `SessionSuggestion` del backend (ver
 * `getSessionSuggestions`) — el coach ve el mismo candidate set que vería
 * abriendo `LinkSessionDialog` desde Actividades. No inventa una heurística
 * de matching nueva.
 */
import { useQuery } from "@tanstack/react-query";

import { getActivities } from "@/api/stravaActivities";

/**
 * "2026-06-15" + offsetDays → "YYYY-MM-DD". Trabaja sobre componentes de
 * fecha calendario locales (sin zona horaria) — `sessionDate` es
 * `TrainingSession.scheduled_date`, un date-only string, no un datetime.
 */
function shiftDate(dateStr: string, offsetDays: number): string {
  const [year, month, day] = dateStr.split("-").map(Number);
  const date = new Date(year, month - 1, day);
  date.setDate(date.getDate() + offsetDays);
  const y = date.getFullYear();
  const m = String(date.getMonth() + 1).padStart(2, "0");
  const d = String(date.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function useUnlinkedActivitiesNearDate(sessionDate: string | undefined, enabled: boolean) {
  return useQuery({
    queryKey: ["unlinked-activities-near-date", sessionDate],
    queryFn: ({ signal }) => {
      const from = shiftDate(sessionDate!, -1);
      const to = shiftDate(sessionDate!, 1);
      return getActivities({ linked: "false", date_from: from, date_to: to }, { signal });
    },
    enabled: enabled && !!sessionDate,
  });
}
