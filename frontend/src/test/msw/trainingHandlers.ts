import { http, HttpResponse } from "msw";

import type {
  Attendance,
  AttendanceStatus,
  MonthlyReportFull,
  ParentMonthlySummary,
  TrainingSession,
} from "@/types/trainingSession.types";

// ---------------------------------------------------------------------------
// Fixture factories
// ---------------------------------------------------------------------------

export function makeSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 10,
    age_group: "u15",
    status: "planned",
    scheduled_date: "2026-05-15",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Pista XCO La Cumbre",
    technical_focus: "Frenada controlada",
    description: "Sesión técnica de frenada",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

export function makeAttendance(overrides?: Partial<Attendance>): Attendance {
  return {
    id: 1,
    session_id: 1,
    athlete_id: 42,
    athlete_name: "Sebastián García",
    status: "presente" as AttendanceStatus,
    rpe_omni: 6,
    rubric_effort: 4,
    rubric_attitude: 4,
    rubric_technique: 3,
    individual_feedback: null,
    excuse_reason: null,
    created_at: "2026-05-15T00:00:00Z",
    updated_at: "2026-05-15T00:00:00Z",
    ...overrides,
  };
}

export function makeMonthlyReport(overrides?: Partial<MonthlyReportFull>): MonthlyReportFull {
  return {
    id: 1,
    club_id: 1,
    year: 2026,
    month: 5,
    ai_summary: "Resumen generado por IA del mes de mayo.",
    metrics_snapshot: {
      total_sessions_planned: 8,
      total_sessions_executed: 7,
      total_sessions_cancelled: 1,
      attendance_stats: [
        { pseudonym: "Atleta A", count_present: 6, count_total: 7, percentage: 85.7 },
      ],
      focos_técnicos: ["Frenada", "Saltos"],
      avg_rpe: 6.5,
      avg_rubric_effort: 3.8,
      avg_rubric_attitude: 4.1,
      avg_rubric_technique: 3.5,
    },
    coach_observations: null,
    generated_by_user_id: 10,
    generated_at: "2026-06-01T00:00:00Z",
    sent_at: null,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// MSW handlers
// ---------------------------------------------------------------------------

export const trainingHandlers = [
  // GET /api/training-sessions — lista con filtros opcionales
  http.get("*/api/training-sessions", () => {
    return HttpResponse.json([makeSession(), makeSession({ id: 2, status: "executed" })]);
  }),

  // GET /api/training-sessions/:id — detalle con asistencias
  http.get("*/api/training-sessions/:id", ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeSession({ id, status: "planned" }));
  }),

  // POST /api/training-sessions — crear sesión
  http.post("*/api/training-sessions", () => {
    return HttpResponse.json(makeSession({ id: 99, status: "planned" }), { status: 201 });
  }),

  // PATCH /api/training-sessions/:id — actualizar sesión
  http.patch("*/api/training-sessions/:id", ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeSession({ id }));
  }),

  // POST /api/training-sessions/:id/execute — ejecutar sesión
  http.post("*/api/training-sessions/:id/execute", ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeSession({ id, status: "executed" }));
  }),

  // DELETE /api/training-sessions/:id — cancelar (204)
  http.delete("*/api/training-sessions/:id", () => {
    return new HttpResponse(null, { status: 204 });
  }),

  // GET /api/training-sessions/:id/attendance — asistencias de sesión
  http.get("*/api/training-sessions/:id/attendance", ({ params }) => {
    const sessionId = Number(params.id);
    return HttpResponse.json([
      makeAttendance({ session_id: sessionId }),
      makeAttendance({ id: 2, session_id: sessionId, athlete_id: 43, athlete_name: "Laura Pérez" }),
    ]);
  }),

  // PUT /api/training-sessions/:id/attendance — convocatoria bulk
  http.put("*/api/training-sessions/:id/attendance", ({ params }) => {
    const sessionId = Number(params.id);
    return HttpResponse.json([makeAttendance({ session_id: sessionId })]);
  }),

  // PATCH /api/training-sessions/:id/attendance/:athleteId — actualizar una asistencia
  http.patch("*/api/training-sessions/:id/attendance/:athleteId", ({ params }) => {
    const sessionId = Number(params.id);
    const athleteId = Number(params.athleteId);
    return HttpResponse.json(makeAttendance({ session_id: sessionId, athlete_id: athleteId }));
  }),

  // POST /api/training-sessions/:id/route-file — subir GPX
  http.post("*/api/training-sessions/:id/route-file", ({ params }) => {
    const id = Number(params.id);
    return HttpResponse.json(makeSession({ id, route_file_path: "/static/routes/1/route.gpx" }));
  }),

  // GET /api/athletes/:id/attendance — historial de asistencia del atleta
  http.get("*/api/athletes/:id/attendance", ({ params }) => {
    const athleteId = Number(params.id);
    return HttpResponse.json([makeAttendance({ athlete_id: athleteId })]);
  }),

  // GET /api/clubs/:id/monthly-reports — lista de reportes
  http.get("*/api/clubs/:id/monthly-reports", () => {
    return HttpResponse.json([makeMonthlyReport(), makeMonthlyReport({ id: 2, month: 4, sent_at: "2026-05-01T10:00:00Z" })]);
  }),

  // GET /api/clubs/:id/monthly-reports/:year/:month — reporte individual
  http.get("*/api/clubs/:id/monthly-reports/:year/:month", ({ params }) => {
    return HttpResponse.json(makeMonthlyReport({ year: Number(params.year), month: Number(params.month) }));
  }),

  // POST /api/clubs/:id/monthly-reports — generar reporte
  http.post("*/api/clubs/:id/monthly-reports", () => {
    return HttpResponse.json(makeMonthlyReport({ id: 10 }), { status: 201 });
  }),

  // POST /api/clubs/:id/monthly-reports/:year/:month/send — enviar reporte
  http.post("*/api/clubs/:id/monthly-reports/:year/:month/send", () => {
    return HttpResponse.json({ enviados: 2, total_admins: 2, sent_at: "2026-06-01T12:00:00Z" });
  }),

  // GET /api/parents/training/monthly-summary/:year/:month — resumen mensual para padre
  http.get("*/api/parents/training/monthly-summary/:year/:month", () => {
    const summary: ParentMonthlySummary = {
      athlete_id: 42,
      athlete_name: "Sebastián García",
      year: 2026,
      month: 5,
      count_present: 6,
      count_total: 7,
      percentage: 85.7,
      focos_técnicos: ["Frenada", "Saltos"],
    };
    return HttpResponse.json([summary]);
  }),
];

// Handler variante para simular 409 en generación de reporte (ya existe)
export const trainingHandlers409 = [
  ...trainingHandlers.filter((h) => !String(h).includes("monthly-reports")),
  http.post("*/api/clubs/:id/monthly-reports", () => {
    return HttpResponse.json(
      { detail: "Ya existe un reporte para este mes" },
      { status: 409 },
    );
  }),
];
