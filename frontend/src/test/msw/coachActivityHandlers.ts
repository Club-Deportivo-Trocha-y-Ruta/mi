/**
 * MSW handlers del informe de actividad por entrenador (feature 041 —
 * gobernanza multi-coach, US7). Contrato:
 * specs/041-multi-coach-governance/contracts/coach-activity-report.md §1.
 *
 * Cubre:
 *   - GET /api/clubs/:clubId/coach-activity
 *
 * Dos entrenadores adultos sintéticos, ninguno con datos de un deportista
 * (ni id, ni nombre, ni fecha de nacimiento) — coherente con el §5 del
 * contrato (privacidad, Ley 1581).
 */
import { http, HttpResponse } from "msw";

import type {
  CoachActivityOut,
  CoachActivityRow,
} from "@/types/coachActivity.types";
import { UserRole } from "@/types/enums";

export function makeCoachActivityRow(
  overrides?: Partial<CoachActivityRow>,
): CoachActivityRow {
  return {
    coach: {
      user_id: 7,
      display_name: "Ana Coach",
      role: UserRole.coach,
      is_active: true,
    },
    sessions: { planned: 1, executed: 6, cancelled: 1, total: 8, co_led: 2 },
    attendance_entries_recorded: 92,
    ai_runs_launched: 4,
    results_operations: { imports: 1, revisions: 3, competitor_links: 2, total: 6 },
    documents: {
      reports_approved: 1,
      newsletters_approved: 7,
      newsletters_sent: 7,
      exports: 4,
    },
    audit_entries_count: 176,
    ...overrides,
  };
}

export function makeCoachActivityOut(
  overrides?: Partial<CoachActivityOut>,
): CoachActivityOut {
  const coaches = overrides?.coaches ?? [
    makeCoachActivityRow(),
    makeCoachActivityRow({
      coach: {
        user_id: 12,
        display_name: "Bruno Coach",
        role: UserRole.coach,
        is_active: true,
      },
      sessions: { planned: 1, executed: 4, cancelled: 0, total: 5, co_led: 2 },
      attendance_entries_recorded: 62,
      ai_runs_launched: 2,
      results_operations: { imports: 1, revisions: 2, competitor_links: 1, total: 4 },
      documents: {
        reports_approved: 0,
        newsletters_approved: 5,
        newsletters_sent: 5,
        exports: 3,
      },
      audit_entries_count: 142,
    }),
  ];

  return {
    club_id: overrides?.club_id ?? 1,
    from: overrides?.from ?? "2026-03-01",
    to: overrides?.to ?? "2026-03-31",
    computed_at: overrides?.computed_at ?? "2026-04-01T14:22:07.913482",
    club_totals: overrides?.club_totals ?? {
      sessions: { planned: 2, executed: 10, cancelled: 1, total: 13 },
      attendance_entries_recorded: 154,
      ai_runs_launched: 6,
      results_operations: { imports: 2, revisions: 5, competitor_links: 3, total: 10 },
      documents: {
        reports_approved: 1,
        newsletters_approved: 12,
        newsletters_sent: 12,
        exports: 7,
      },
      audit_entries_count: 318,
    },
    coaches,
  };
}

/** Vacío pero `200`: club sin actividad en el período, sin entrenadores. */
export function makeEmptyCoachActivityOut(
  overrides?: Partial<CoachActivityOut>,
): CoachActivityOut {
  return makeCoachActivityOut({
    club_totals: {
      sessions: { planned: 0, executed: 0, cancelled: 0, total: 0 },
      attendance_entries_recorded: 0,
      ai_runs_launched: 0,
      results_operations: { imports: 0, revisions: 0, competitor_links: 0, total: 0 },
      documents: {
        reports_approved: 0,
        newsletters_approved: 0,
        newsletters_sent: 0,
        exports: 0,
      },
      audit_entries_count: 0,
    },
    coaches: [],
    ...overrides,
  });
}

export const getCoachActivityHandler = http.get(
  "*/api/clubs/:clubId/coach-activity",
  ({ request }) => {
    const url = new URL(request.url);
    const coachUserId = url.searchParams.get("coach_user_id");

    if (coachUserId) {
      const row = makeCoachActivityOut().coaches.find(
        (c) => c.coach.user_id === Number(coachUserId),
      );
      return HttpResponse.json(
        makeCoachActivityOut({ coaches: row ? [row] : [] }),
      );
    }

    return HttpResponse.json(makeCoachActivityOut());
  },
);

export const coachActivityErrorHandler = http.get(
  "*/api/clubs/:clubId/coach-activity",
  () =>
    HttpResponse.json(
      { detail: "No se pudo cargar la actividad por entrenador." },
      { status: 500 },
    ),
);

export const coachActivityHandlers = [getCoachActivityHandler];
