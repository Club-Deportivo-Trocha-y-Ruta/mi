/**
 * Fixtures para insights v2 (race_analyst_v2) — Task #9.
 *
 * Formato esperado del summary_text v2: markdown con 4 headers ##:
 *   ## Qué pasó
 *   ## Recorrido hasta aquí
 *   ## Hacia dónde va
 *   ## Resumen de temporada
 *
 * El parsing al cliente vive en InsightsTimeline.tsx (parseV2Sections).
 */
import type {
  AthleteInsightDetailOut,
  AthleteInsightOut,
} from "@/types/athleteRaceAnalysis.types";

/**
 * Helper para componer un summary_text v2 con bloques personalizables.
 * Si una sección viene vacía, igual emite el header (test de no-render).
 */
export function buildV2Markdown(opts?: {
  whatHappened?: string;
  journeySoFar?: string;
  lookingAhead?: string;
  seasonSummary?: string;
}): string {
  const w = opts?.whatHappened ?? "Avanzó en frenada y curvas cerradas.";
  const j = opts?.journeySoFar ?? "Progreso técnico consistente desde V1.";
  const l =
    opts?.lookingAhead ?? "Foco en cadencia sostenida para las próximas válidas.";
  const s = opts?.seasonSummary ?? "Temporada de aprendizaje con disfrute.";
  return (
    `## Qué pasó\n${w}\n\n` +
    `## Recorrido hasta aquí\n${j}\n\n` +
    `## Hacia dónde va\n${l}\n\n` +
    `## Resumen de temporada\n${s}\n`
  );
}

export function mockInsightV2(
  overrides?: Partial<AthleteInsightOut>,
): AthleteInsightOut {
  return {
    id: 1001,
    season: 2026,
    valida_num: 4,
    event_id: 104,
    use_case: "race_analysis",
    summary_text: buildV2Markdown(),
    confidence: "high",
    model: "gemini-2.5-flash-lite",
    prompt_version: "race_analyst_v2",
    coach_approved: true,
    generated_at: "2026-05-20T10:00:00Z",
    approved_at: "2026-05-20T12:30:00Z",
    is_active: true,
    deprecated_at: null,
    ...overrides,
  };
}

export function mockInsightV2Detail(
  overrides?: Partial<AthleteInsightDetailOut>,
): AthleteInsightDetailOut {
  const base = mockInsightV2();
  return {
    ...base,
    recommendations: [
      { text: "Mantener cadencia >75 rpm en tramos rodantes." },
      { text: "Trabajar transferencia de peso en peraltes." },
    ],
    metrics_snapshot: { schema_version: 1, season: 2026 } as never,
    principles_cited: [],
    supersedes: [],
    superseded_by: null,
    // Task #22: defaults consistentes. Override en cada test para escenarios
    // N=1 (true) vs atleta con historial (false) vs legacy v1 (null).
    is_first_in_season: false,
    season_validas_count: 3,
    ...overrides,
  };
}

/**
 * 5 insights v2 con summary_text DIFERENTE en cada uno — para verificar
 * que la preview por card es distinta (no replicada).
 */
export function buildFiveDistinctV2Insights(): AthleteInsightOut[] {
  return [1, 2, 3, 4, 5].map((valida) =>
    mockInsightV2({
      id: 1000 + valida,
      valida_num: valida,
      generated_at: `2026-0${valida}-15T10:00:00Z`,
      summary_text: buildV2Markdown({
        whatHappened: `Válida ${valida}: foco específico de la jornada ${valida}.`,
        journeySoFar: `Hasta Válida ${valida}, tendencia positiva sostenida.`,
        lookingAhead: `Próximo objetivo tras Válida ${valida}: técnica.`,
        seasonSummary: `Resumen acumulado al cierre de Válida ${valida}.`,
      }),
    }),
  );
}

/**
 * Season summary insight (valida_num=0, use_case=season_summary).
 * Generado por el endpoint POST /season-summary.
 */
export function mockSeasonSummaryInsight(
  overrides?: Partial<AthleteInsightOut>,
): AthleteInsightOut {
  return mockInsightV2({
    id: 9000,
    valida_num: 0,
    use_case: "season_summary",
    event_id: null,
    summary_text: buildV2Markdown({
      seasonSummary:
        "Temporada con progreso técnico claro y mejora en cadencia. " +
        "Foco 2026: consistencia en válidas Tipo A.",
    }),
    ...overrides,
  });
}
