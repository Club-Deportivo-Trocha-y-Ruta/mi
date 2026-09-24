/**
 * RaceInsightEmailRedirect — alias de deep link para correos de insight de
 * carrera ya enviados.
 *
 * Ruta: /athletes/:athleteId/race-analysis/insights/:insightId
 *
 * Contexto (2026-09-23): hasta ahora, el correo que se enviaba a los padres
 * al aprobar un insight (válidas tier A/CD) apuntaba a esta ruta — que
 * nunca existió en el router y terminaba en NotFoundPage. Aprobar un
 * insight ya no envía correo (ver
 * `backend/app/services/notification/race_insight_dispatcher.py`), pero
 * los correos que YA se enviaron antes de ese cambio siguen circulando en
 * bandejas de entrada. Este alias los redirige al panorama correcto según
 * el rol de quien haga clic, en vez de dejarlos varados en un 404.
 *
 * Sesión:
 *   - Montada bajo `<ProtectedRoute>` sin `allowedRoles` (mismo patrón que
 *     `/perfil` en App.tsx) — cualquier rol autenticado puede llegar aquí.
 *   - Sin sesión activa, `ProtectedRoute` ya redirige a `/login` guardando
 *     esta ruta en `state.from`; `LoginPage` vuelve aquí tras autenticar
 *     (ver `routes/auth/LoginPage.tsx`).
 *
 * Destino final según rol (feature 045, T043 — pestaña única «Carreras»,
 * vista «Análisis IA», con el análisis expandido):
 *   - parent      → /my-athletes/:athleteId?tab=races&view=analisis&insight=:id
 *   - coach/admin → /athletes/:athleteId?tab=races&view=analisis&insight=:id
 *   - cualquier otro rol (ej. athlete, que no debería recibir este correo)
 *     → NotFoundPage — no existe un panorama de atleta para ese rol.
 */
import { Navigate, useParams } from "react-router-dom";

import { NotFoundPage } from "@/routes/NotFoundPage";
import { useAuthStore } from "@/store/auth.store";
import { UserRole } from "@/types/enums";

export function RaceInsightEmailRedirect() {
  const { athleteId, insightId } = useParams<{
    athleteId: string;
    insightId: string;
  }>();
  const role = useAuthStore((s) => s.user?.role);

  if (!athleteId || !insightId) {
    return <NotFoundPage />;
  }

  if (role === UserRole.parent) {
    return (
      <Navigate
        to={`/my-athletes/${athleteId}?tab=races&view=analisis&insight=${insightId}`}
        replace
      />
    );
  }

  if (role === UserRole.coach || role === UserRole.admin) {
    return (
      <Navigate
        to={`/athletes/${athleteId}?tab=races&view=analisis&insight=${insightId}`}
        replace
      />
    );
  }

  return <NotFoundPage />;
}
