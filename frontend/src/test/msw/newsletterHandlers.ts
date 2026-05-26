/**
 * MSW handlers para el módulo Boletín Mensual Individual por Atleta (Fase 1.8).
 *
 * Privacy constraint: `sent_to` NUNCA debe aparecer en ninguna respuesta.
 */
import { http, HttpResponse } from "msw";

import type {
  AthleteNewsletter,
  AiNarrative,
  AttachInsightsRequest,
  AttachInsightsResponse,
  BatchResult,
  NarrativeOverride,
  NewsletterStatus,
} from "@/types/athleteNewsletter.types";

// ---------------------------------------------------------------------------
// Fixture factory
// ---------------------------------------------------------------------------

export function makeNewsletter(
  overrides?: Partial<AthleteNewsletter>,
): AthleteNewsletter {
  const base: AthleteNewsletter = {
    id: 1,
    athlete_id: 42,
    year: 2026,
    month: 4,
    status: "draft",
    email_blocks: {
      attendance: {
        attendance_pct: 85.7,
        prev_month_pct: 80.0,
        streak_sessions: 3,
        count_present: 6,
        count_total: 7,
      },
      technical_load: {
        focos_tecnicos: ["Frenada", "Curvas"],
        avg_rpe: 6.5,
        avg_rubric_effort: 3.8,
        avg_rubric_attitude: 4.1,
        avg_rubric_technique: 3.5,
      },
      races: {
        races: [
          {
            event_name: "Válida IV — Cali",
            event_date: "2026-05-17",
            position: 3,
            category: "JUV-M",
            gap_p1_ms: 45000,
            gap_p3_ms: 0,
          },
        ],
        ranking_club: 2,
        projection: "Mantener ritmo para top-5 en Válida V.",
      },
      calendar: {
        next_race_name: "Válida V — Palmira",
        next_race_date: "2026-08-01",
        next_race_location: "Palmira, Valle del Cauca",
        macro_phase: "Competitiva A",
        planned_sessions_next_month: 8,
      },
      support_at_home: {
        tips: [
          "Asegúrate de que tu hijo duerma 9-10 horas antes de las sesiones.",
          "Lleva suficiente agua: mínimo 1.5L para salidas largas.",
        ],
        hydration_reminder:
          "Hidratación: agua y frutas antes de entrenar; no bebidas azucaradas.",
        sleep_reminder: "Sueño reparador: clave para la recuperación muscular.",
      },
      photos: {
        photos: [
          {
            media_id: 1,
            thumbnail_url: null,
            caption: "Sesión técnica del 15 de abril",
          },
        ],
        total: 3,
      },
    },
    ai_narrative: {
      strengths:
        "Demostró constancia en las sesiones y mejoró su técnica de descenso.",
      area_to_develop: "Trabajar la cadencia en subidas largas.",
      milestone: "Primera sesión completa sin parar en el circuito técnico.",
      model: "gemini-2.5-flash-lite",
      prompt_version: "v1",
      confidence: "medium",
    } as AiNarrative,
    coach_narrative_overrides: null,
    badges_earned: [
      { badge_type: "attendance_90", label: "Asistencia 90%", description: "90% o más este mes" },
    ],
    has_pdf: false,
    pdf_generated_at: null,
    pdf_sha256: null,
    generated_by_user_id: 10,
    approved_by_user_id: null,
    approved_at: null,
    sent_at: null,
    error_message: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    // NOTE: sent_to is intentionally ABSENT — PII, never in API response
    ...overrides,
  };
  return base;
}

export function makeBatchResult(overrides?: Partial<BatchResult>): BatchResult {
  return {
    period_year: 2026,
    period_month: 4,
    total_athletes: 5,
    created: 4,
    skipped: 1,
    failed: 0,
    newsletter_ids: [1, 2, 3, 4],
    errors: [],
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export const newsletterHandlers = [
  // GET /api/athletes/:athleteId/monthly-newsletters — lista
  http.get("*/api/athletes/:athleteId/monthly-newsletters", ({ params }) => {
    const athleteId = Number(params.athleteId);
    return HttpResponse.json([
      makeNewsletter({ athlete_id: athleteId }),
      makeNewsletter({
        id: 2,
        athlete_id: athleteId,
        month: 3,
        status: "sent",
        sent_at: "2026-04-10T10:00:00Z",
      }),
    ]);
  }),

  // GET /api/athletes/:athleteId/monthly-newsletters/:id — detalle
  http.get(
    "*/api/athletes/:athleteId/monthly-newsletters/:id",
    ({ params }) => {
      const athleteId = Number(params.athleteId);
      const id = Number(params.id);
      return HttpResponse.json(makeNewsletter({ id, athlete_id: athleteId }));
    },
  ),

  // POST /api/athletes/:athleteId/monthly-newsletters — crear
  http.post(
    "*/api/athletes/:athleteId/monthly-newsletters",
    ({ params }) => {
      const athleteId = Number(params.athleteId);
      return HttpResponse.json(
        makeNewsletter({ id: 99, athlete_id: athleteId }),
        { status: 201 },
      );
    },
  ),

  // PATCH /api/athletes/:athleteId/monthly-newsletters/:id — editar narrativa
  http.patch(
    "*/api/athletes/:athleteId/monthly-newsletters/:id",
    async ({ params, request }) => {
      const athleteId = Number(params.athleteId);
      const id = Number(params.id);
      const body = (await request.json()) as { coach_narrative_overrides: NarrativeOverride };
      return HttpResponse.json(
        makeNewsletter({
          id,
          athlete_id: athleteId,
          coach_narrative_overrides: body.coach_narrative_overrides,
        }),
      );
    },
  ),

  // POST /api/athletes/:athleteId/monthly-newsletters/:id/approve
  http.post(
    "*/api/athletes/:athleteId/monthly-newsletters/:id/approve",
    ({ params }) => {
      const athleteId = Number(params.athleteId);
      const id = Number(params.id);
      return HttpResponse.json(
        makeNewsletter({
          id,
          athlete_id: athleteId,
          status: "approved" as NewsletterStatus,
          approved_by_user_id: 10,
          approved_at: new Date().toISOString(),
        }),
      );
    },
  ),

  // POST /api/athletes/:athleteId/monthly-newsletters/:id/send
  http.post(
    "*/api/athletes/:athleteId/monthly-newsletters/:id/send",
    ({ params }) => {
      const athleteId = Number(params.athleteId);
      const id = Number(params.id);
      return HttpResponse.json(
        makeNewsletter({
          id,
          athlete_id: athleteId,
          status: "sent" as NewsletterStatus,
          sent_at: new Date().toISOString(),
        }),
      );
    },
  ),

  // GET /api/athletes/:athleteId/monthly-newsletters/:id/pdf — binary PDF
  http.get(
    "*/api/athletes/:athleteId/monthly-newsletters/:id/pdf",
    () => {
      // Simulate a small PDF binary
      const pdfContent = new Uint8Array([0x25, 0x50, 0x44, 0x46]); // %PDF header
      return new HttpResponse(pdfContent, {
        status: 200,
        headers: {
          "Content-Type": "application/pdf",
          "Content-Disposition": "attachment; filename=boletin.pdf",
        },
      });
    },
  ),

  // POST /api/clubs/:clubId/monthly-newsletters/batch
  http.post(
    "*/api/clubs/:clubId/monthly-newsletters/batch",
    () => {
      return HttpResponse.json(makeBatchResult(), { status: 201 });
    },
  ),

  // POST /api/athletes/:athleteId/monthly-newsletters/attach-insights
  http.post(
    "*/api/athletes/:athleteId/monthly-newsletters/attach-insights",
    async ({ params, request }) => {
      const athleteId = Number(params.athleteId);
      const body = (await request.json()) as AttachInsightsRequest;
      const response: AttachInsightsResponse = {
        newsletter_id: 42,
        athlete_id: athleteId,
        year: 2026,
        month: 5,
        status: "pending",
        selected_race_insight_ids: body.insight_ids,
        created: true,
      };
      return HttpResponse.json(response);
    },
  ),
];

// ---------------------------------------------------------------------------
// Variant handlers for error scenarios
// ---------------------------------------------------------------------------

/** Handler que simula 409 por hermano en draft al enviar */
export const sendSiblingBlockedHandler = http.post(
  "*/api/athletes/:athleteId/monthly-newsletters/:id/send",
  () => {
    return HttpResponse.json(
      {
        detail:
          "El padre de este atleta tiene otro hijo con boletín en draft. Usa force_individual=true para enviar individualmente.",
      },
      { status: 409 },
    );
  },
);

/** Handler que simula 409 en creación (ya existe) */
export const createConflictHandler = http.post(
  "*/api/athletes/:athleteId/monthly-newsletters",
  () => {
    return HttpResponse.json(
      { detail: "Ya existe un boletín para este período." },
      { status: 409 },
    );
  },
);

/** Handler que simula 403 */
export const forbiddenHandler = http.get(
  "*/api/athletes/:athleteId/monthly-newsletters",
  () => {
    return HttpResponse.json(
      { detail: "No tienes permiso para acceder a este recurso." },
      { status: 403 },
    );
  },
);

/** Handler que simula 404 */
export const notFoundHandler = http.get(
  "*/api/athletes/:athleteId/monthly-newsletters/:id",
  () => {
    return HttpResponse.json({ detail: "Not found" }, { status: 404 });
  },
);

/** Handler que simula 400 en attach-insights por insight_ids inválidos */
export const attachInsightsInvalidHandler = http.post(
  "*/api/athletes/:athleteId/monthly-newsletters/attach-insights",
  () => {
    return HttpResponse.json(
      { detail: { invalid_ids: [4, 5] } },
      { status: 400 },
    );
  },
);

/** Handler que simula 403 en attach-insights (intento de parent) */
export const attachInsightsForbiddenHandler = http.post(
  "*/api/athletes/:athleteId/monthly-newsletters/attach-insights",
  () => {
    return HttpResponse.json(
      { detail: "No tienes permiso para realizar esta acción." },
      { status: 403 },
    );
  },
);
