/**
 * Fixture de StageLog v2 para specs que mockean el boletín («Bitácora de
 * etapa», feature 038). `AthleteNewsletterStudioPage` renderiza el estado
 * «Esta bitácora todavía no tiene contenido generado» —sin el `<h1>` «Bitácora
 * de {mes} {año}»— cuando `stage_log` es `null` (ver
 * `frontend/src/routes/training/AthleteNewsletterStudioPage.tsx`), así que
 * cualquier mock de `GET /api/athletes/:id/monthly-newsletters/:id` que espere
 * ver el estudio debe devolver un `stage_log` completo.
 *
 * Datos 100 % ficticios (privacidad de menores, CLAUDE.md).
 */
export function makeStageLog(coachNote: string | null = null) {
  return {
    schema_version: 2,
    stage_number: 3,
    period_label: "Mayo 2026",
    is_current_month: false,
    athlete_first_name: "Atleta Demo",
    athlete_reference: "su hija",
    stage_title: "Un mes de trabajo técnico sostenido",
    trail: [],
    summit: null,
    observations: [
      {
        claim: "La asistencia se mantuvo estable durante el mes.",
        evidence: "8 de 9 sesiones planificadas (89 %)",
        block_ref: "attendance",
      },
    ],
    analyst_reading: null,
    effort_profile: [],
    next_segment: null,
    family_compass: null,
    badges: [],
    photos: [],
    coach_note: coachNote,
    block_states: {
      stage_title: "ai",
      summit_caption: "empty",
      observations: "ai",
      analyst_reading: "empty",
      next_segment_text: "empty",
      family_compass: "empty",
    },
    grounding_violations: [],
  };
}
