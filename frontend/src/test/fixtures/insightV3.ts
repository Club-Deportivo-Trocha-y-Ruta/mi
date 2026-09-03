/**
 * Fixtures de InsightV3 estructurado (feature 037, T205).
 *
 * Todos los datos son 100% ficticios (privacidad de menores, CLAUDE.md):
 * ningún nombre real, sin peso/IMC en ningún campo.
 */
import type {
  AthleteInsightDetailOut,
  AthleteInsightOut,
} from "@/types/athleteRaceAnalysis.types";
import type { InsightV3 } from "@/types/insightV3.types";

export function buildInsightV3(overrides?: Partial<InsightV3>): InsightV3 {
  return {
    schema_version: "v3",
    headline: "Progreso técnico sostenido en frenada y curvas cerradas.",
    field_reading: {
      percentile: 62.5,
      expected_position: 5,
      actual_position: 4,
      delta_vs_expected: 1,
      gap_to_p3_hhmmss: "00:01:12",
      series_label: "Válida IV · Copa Valle",
      summary: "Terminó 4to de 12, un puesto por encima de lo esperado.",
    },
    trend: "improving",
    observations: [
      {
        claim: "La cadencia en tramos rodantes se mantuvo estable sobre 78 rpm.",
        evidence: ["cadencia media 78 rpm (vs 71 rpm en Válida III)"],
        domain: "field",
        confidence: "high",
      },
      {
        claim: "El tiempo de recuperación entre sesiones de intervalos mejoró.",
        evidence: ["3 sesiones de intervalos en 28 días", "RPE medio 6.2/10"],
        domain: "training",
        confidence: "medium",
      },
    ],
    actions: [
      {
        text: "Practicar frenada progresiva en 2 sesiones técnicas de 20 min esta semana.",
        category: "technique",
        priority: "high",
        horizon: "next_week",
        catalog_ref: { kind: "interval_template", code: "12", label: "Base aeróbica" },
        derived_from: 0,
      },
      {
        text: "Sumar un bloque de fuerza de tren inferior antes de la próxima válida.",
        category: "volume",
        priority: "med",
        horizon: "next_race",
        catalog_ref: null,
        derived_from: 1,
      },
    ],
    watch_signals: ["Vigilar fatiga acumulada si sube a 4 sesiones semanales."],
    coach_question: "¿Cómo se sintió con el ritmo en el tramo técnico final?",
    data_gaps: [],
    principles_cited: ["Periodización juvenil", "Carga por RPE"],
    ...overrides,
  };
}

export function buildSeasonInsightV3(overrides?: Partial<InsightV3>): InsightV3 {
  return buildInsightV3({
    headline: "Temporada de consolidación técnica con margen de mejora en ritmo.",
    field_reading: null,
    trend: "mixed",
    coach_question: "¿Qué aspecto priorizamos de cara a la pretemporada?",
    ...overrides,
  });
}

/**
 * `mockInsightV3` / `mockInsightV3Detail` siguen el patrón de
 * `test/fixtures/insightV2.ts` — factory con overrides parciales.
 */
export function mockInsightV3(
  overrides?: Partial<AthleteInsightOut>,
): AthleteInsightOut {
  const structured = buildInsightV3();
  return {
    id: 2001,
    season: 2026,
    valida_num: 4,
    event_id: 204,
    event_date: "2026-05-17",
    series_kind: "cup",
    use_case: "race_analysis",
    summary_text: structured.headline,
    confidence: "high",
    model: "gemini-3.8-flash",
    prompt_version: "race_analyst_v3",
    coach_approved: true,
    generated_at: "2026-05-20T10:00:00Z",
    approved_at: "2026-05-20T12:30:00Z",
    is_active: true,
    deprecated_at: null,
    is_fallback: false,
    headline: structured.headline,
    coach_rating: null,
    ...overrides,
  };
}

export function mockInsightV3Detail(
  overrides?: Partial<AthleteInsightDetailOut>,
  structuredOverrides?: Partial<InsightV3>,
): AthleteInsightDetailOut {
  const base = mockInsightV3();
  const structured = buildInsightV3(structuredOverrides);
  return {
    ...base,
    recommendations: [],
    metrics_snapshot: { schema_version: 1, season: 2026 } as never,
    principles_cited: [],
    supersedes: [],
    superseded_by: null,
    is_first_in_season: false,
    season_validas_count: 4,
    structured,
    coach_answer_text: null,
    coach_answer_at: null,
    ...overrides,
  };
}

/**
 * 5 insights v3 con `structured` DISTINTO cada uno (headline, actions,
 * observations, trend) — verifica que cada preview/drawer muestre
 * contenido único y no un fixture replicado.
 */
export function buildFiveDistinctV3Insights(): AthleteInsightOut[] {
  const scenarios: Array<Partial<InsightV3>> = [
    {
      headline: "Frenada técnica más consistente que en válidas previas.",
      trend: "improving",
    },
    {
      headline: "Caída de posición explicada por un pinchazo, no por forma física.",
      trend: "declining",
      watch_signals: ["Revisar presión de llantas antes de la próxima carrera."],
    },
    {
      headline: "Rendimiento estable con margen de mejora en subidas técnicas.",
      trend: "stable",
    },
    {
      headline: "Primer resultado de la temporada: aún sin punto de comparación.",
      trend: "first_reference",
      field_reading: null,
    },
    {
      headline: "Mezcla de señales: mejor ritmo, pero más nervios en la salida.",
      trend: "mixed",
    },
  ];
  return scenarios.map((s, idx) => {
    const valida = idx + 1;
    const structured = buildInsightV3(s);
    return mockInsightV3({
      id: 2000 + valida,
      valida_num: valida,
      event_id: 200 + valida,
      generated_at: `2026-0${valida}-15T10:00:00Z`,
      headline: structured.headline,
      summary_text: structured.headline,
    });
  });
}

export function mockSeasonInsightV3(
  overrides?: Partial<AthleteInsightOut>,
): AthleteInsightOut {
  const structured = buildSeasonInsightV3();
  return mockInsightV3({
    id: 2900,
    valida_num: 0,
    use_case: "season_summary",
    event_id: null,
    event_date: null,
    series_kind: null,
    headline: structured.headline,
    summary_text: structured.headline,
    ...overrides,
  });
}
