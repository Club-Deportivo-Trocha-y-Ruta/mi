/**
 * MSW handlers para el agregado de mission-control del coach (feature 031).
 *
 * Cubre el endpoint:
 *   - GET /api/dashboard/coach-summary → CoachSummary
 *
 * Privacy constraint: el payload es solo conteos y minutos por banda —
 * jamás nombres/ids de atletas ni contenido de sesiones (FR-010).
 */
import { http, HttpResponse } from "msw";

import type { CoachSummary, WeeklyLoadBand } from "@/types/dashboard.types";

// ---------------------------------------------------------------------------
// Fixture factory
// ---------------------------------------------------------------------------

export function makeWeeklyLoadBand(
  overrides?: Partial<WeeklyLoadBand>,
): WeeklyLoadBand {
  return {
    age_band: "10-12",
    planned_minutes: 240,
    cap_minutes: 600,
    athlete_count: 8,
    ...overrides,
  };
}

export function makeCoachSummary(
  overrides?: Partial<CoachSummary>,
): CoachSummary {
  return {
    generated_at: "2026-07-11T20:03:00Z",
    consents_pending: 3,
    insights_stale: 1,
    weekly_load: [
      makeWeeklyLoadBand(),
      makeWeeklyLoadBand({
        age_band: "13-15",
        planned_minutes: 810,
        cap_minutes: 780,
        athlete_count: 6,
      }),
    ],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Handlers por defecto (escenario feliz — todos los campos poblados)
// ---------------------------------------------------------------------------

const BASE = "*/api/dashboard/coach-summary";

const coachSummaryHandler = http.get(BASE, () => {
  return HttpResponse.json(makeCoachSummary());
});

/** Conjunto de handlers del escenario feliz — registrar en setup global. */
export const dashboardHandlers = [coachSummaryHandler];

// ---------------------------------------------------------------------------
// Handlers de escenarios alternativos — importar por suite según necesidad
// ---------------------------------------------------------------------------

/**
 * GET → un campo en `null` (fallo aislado de una sub-computación, ej.
 * `weekly_load`), mientras los otros dos siguen poblados. Ejercita el
 * degradado parcial del contrato (FR-004 / data-model.md §1).
 */
export const coachSummaryPartialNullHandler = http.get(BASE, () => {
  return HttpResponse.json(
    makeCoachSummary({ weekly_load: null }),
  );
});

/**
 * GET 403 — rol distinto de coach/admin, o coach pidiendo un `club_id`
 * ajeno (contract "RBAC").
 */
export const coachSummaryForbiddenHandler = http.get(BASE, () => {
  return HttpResponse.json(
    { detail: "No tienes permiso para acceder a este recurso." },
    { status: 403 },
  );
});

/**
 * GET 500 — error genérico del servidor para `coach-summary` completo (no un
 * campo aislado como `coachSummaryPartialNullHandler`, sino la fuente
 * entera). Ejercita el degradado silencioso de las dos filas del inbox que
 * dependen de este agregado ("Consentimientos pendientes" / "Insights IA
 * desactualizados", T036): ambas deben omitirse sin banner de error ni
 * bloquear el resto del inbox (US2 acceptance #2, FR-004,
 * `contracts/home-tiles.md` §"Degraded state").
 */
export const coachSummaryServerErrorHandler = http.get(BASE, () => {
  return new HttpResponse(null, { status: 500 });
});

/**
 * GET /api/activities → 500 — cubre la fila "Actividades sin enlazar"
 * (T034), que consulta este mismo endpoint en modo *count-only*
 * (`useActivityReview({linked:"false", page:1, page_size:1})`, solo se usa
 * `.total`) vía `PendingInbox`. Al fallar, esa fila se omite igual que
 * cualquier otra fuente no disponible — el resto del inbox sigue visible
 * (US2 acceptance #2, FR-004). No coincide con `BASE`
 * (`/api/dashboard/coach-summary`): es un endpoint distinto, reexpuesto acá
 * para que las pruebas de `PendingInbox` compongan sus escenarios
 * degradados sin importar de `stravaHandlers.ts`.
 */
export const activitiesCountOnlyErrorHandler = http.get("*/api/activities", () => {
  return new HttpResponse(null, { status: 500 });
});
