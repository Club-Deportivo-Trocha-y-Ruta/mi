/**
 * MSW handlers para el módulo athlete-race-analysis (FE-1).
 *
 * Mock data realista que respeta los shapes de
 * ``@/types/athleteRaceAnalysis.types``. Helpers factory para
 * sobreescribir campos puntuales por suite.
 *
 * Estos handlers NO se registran por default en el server global —
 * cada suite los importa y los empuja con ``mswServer.use(...)`` para
 * evitar interferir con tests existentes.
 */
import { http, HttpResponse } from "msw";

import type {
  AthleteInsightDetailOut,
  AthleteInsightListResponse,
  AthleteInsightOut,
  AthleteRunListResponse,
  AthleteRunOut,
  AvailableRaceEvent,
  ClubInsightsByRaceResponse,
  DistributionResponse,
  EvolutionResponse,
  MetricsSnapshotV1,
  RaceParticipationResponse,
  SeasonPanoramaResponse,
} from "@/types/athleteRaceAnalysis.types";

// ---------------------------------------------------------------------------
// Factory helpers
// ---------------------------------------------------------------------------

export function mockMetricsSnapshot(
  overrides?: Partial<MetricsSnapshotV1>,
): MetricsSnapshotV1 {
  return {
    schema_version: 1,
    event_id: 100,
    season: 2026,
    valida_num: 4,
    event_date: "2026-05-17",
    status: "finished",
    race_time_ms: 1_800_000,
    position: 3,
    podium_gap_ms: 45_000,
    ranking_in_category: 3,
    category_id: 10,
    category_code: "JUV-M",
    category_size: 8,
    category_time_mean_ms: 1_900_000,
    category_time_stddev_ms: 60_000,
    category_time_min_ms: 1_750_000,
    category_time_max_ms: 2_100_000,
    extras: {},
    ...overrides,
  };
}

export function mockInsight(
  overrides?: Partial<AthleteInsightOut>,
): AthleteInsightOut {
  // `series_kind` sigue a `valida_num` cuando el caller no lo pasa
  // explícito: varios tests pre-existentes overridean solo `valida_num: 99`
  // (convención retirada, feature 036 T030) esperando trato departamental,
  // y un default fijo en "cup" los dejaría con una combinación imposible en
  // datos reales (backend nunca emite valida_num=99 + series_kind="cup").
  const finalValidaNum = overrides?.valida_num ?? 4;
  const defaultSeriesKind: AthleteInsightOut["series_kind"] =
    finalValidaNum === 99 ? "championship" : "cup";
  return {
    id: 1,
    season: 2026,
    valida_num: 4,
    event_id: 100,
    event_date: "2026-05-17",
    series_kind: defaultSeriesKind,
    use_case: "race_analysis",
    summary_text:
      "Resumen del desempeño del deportista en Válida IV. Mostró " +
      "progreso técnico en frenada y mantuvo cadencia >75 rpm en subidas.",
    confidence: "high",
    model: "gemini-2.5-flash-lite",
    prompt_version: "v1.2",
    coach_approved: true,
    generated_at: "2026-05-18T10:00:00Z",
    approved_at: "2026-05-18T12:30:00Z",
    is_active: true,
    deprecated_at: null,
    is_fallback: false,
    ...overrides,
  };
}

/**
 * Texto placeholder exacto persistido por `deterministic_fallback`
 * (`backend/app/services/race/ai/fallback.py`) cuando el analyst LLM falla.
 * Mantenido en sync manualmente — no hay import cross-lenguaje posible.
 */
export const FALLBACK_SUMMARY_TEXT =
  "Análisis IA no disponible en este momento. Revisa los datos crudos " +
  "en la sección de resultados.";

/**
 * Insight fallback (US4, feature 036) — persistido por el camino de FALLA
 * de `deterministic_fallback`: `is_fallback=true` y `summary_text` es el
 * placeholder fijo, no un análisis real. Confianza forzada a "low" por el
 * crítico ante secciones vacías (`critic_agent.py`).
 */
export function mockFallbackInsight(
  overrides?: Partial<AthleteInsightOut>,
): AthleteInsightOut {
  return mockInsight({
    id: 77,
    valida_num: 3,
    confidence: "low",
    prompt_version: "race_analyst_v2",
    summary_text: FALLBACK_SUMMARY_TEXT,
    is_fallback: true,
    ...overrides,
  });
}

/**
 * Variante fallback del resumen de temporada (`valida_num=0`) — el resumen
 * on-demand (`invoke_season_summary`) también puede caer al fallback
 * determinista cuando el LLM falla.
 */
export function mockFallbackSeasonSummaryInsight(
  overrides?: Partial<AthleteInsightOut>,
): AthleteInsightOut {
  return mockFallbackInsight({
    id: 78,
    valida_num: 0,
    event_id: null,
    event_date: null,
    series_kind: null,
    use_case: "season_summary_v2",
    ...overrides,
  });
}

export function mockInsightDetail(
  overrides?: Partial<AthleteInsightDetailOut>,
): AthleteInsightDetailOut {
  const base = mockInsight();
  return {
    ...base,
    recommendations: [
      { text: "Mantener trabajo de cadencia en zona Z2." },
      { text: "Foco técnico próxima sesión: peraltes y curvas cerradas." },
    ],
    metrics_snapshot: mockMetricsSnapshot(),
    principles_cited: [
      { id: "ltad-1", text: "Edad biológica > edad cronológica" },
    ],
    supersedes: [],
    superseded_by: null,
    ...overrides,
  };
}

/** Detalle de un insight fallback (US4, feature 036) — ver `mockFallbackInsight`. */
export function mockFallbackInsightDetail(
  overrides?: Partial<AthleteInsightDetailOut>,
): AthleteInsightDetailOut {
  return {
    ...mockFallbackInsight(),
    recommendations: [],
    metrics_snapshot: mockMetricsSnapshot(),
    principles_cited: [],
    supersedes: [],
    superseded_by: null,
    ...overrides,
  };
}

export function mockRun(overrides?: Partial<AthleteRunOut>): AthleteRunOut {
  return {
    run_id: "run-abc123",
    status: "completed",
    season: 2026,
    valida_nums: [4],
    started_at: "2026-05-18T09:55:00Z",
    finished_at: "2026-05-18T10:00:00Z",
    explain_mode: false,
    has_output: true,
    ...overrides,
  };
}

export function mockEvolution(
  overrides?: Partial<EvolutionResponse>,
): EvolutionResponse {
  return {
    season: 2026,
    metric: "podium_gap_ms",
    confidence: "high",
    series: [
      {
        valida_num: 1,
        event_id: 91,
        event_date: "2026-01-31",
        value: 120_000,
        unit: "ms",
        series_kind: "cup",
        label: "Válida I — Sevilla",
      },
      {
        valida_num: 2,
        event_id: 92,
        event_date: "2026-02-28",
        value: 95_000,
        unit: "ms",
        series_kind: "cup",
        label: "Válida II — Ginebra",
      },
      {
        valida_num: 3,
        event_id: 93,
        event_date: "2026-04-19",
        value: 60_000,
        unit: "ms",
        series_kind: "cup",
        label: "Válida III — La Cumbre",
      },
      {
        valida_num: 4,
        event_id: 94,
        event_date: "2026-05-17",
        value: 45_000,
        unit: "ms",
        series_kind: "cup",
        label: "Válida IV — Cali",
      },
    ],
    ...overrides,
  };
}

export function mockDistribution(
  overrides?: Partial<DistributionResponse>,
): DistributionResponse {
  return {
    season: 2026,
    event_id: 100,
    category_id: 10,
    category_code: "JUV-M",
    sample_size: 8,
    mean_ms: 1_900_000,
    stddev_ms: 60_000,
    athlete_time_ms: 1_800_000,
    athlete_z_score: -1.67,
    athlete_percentile: 80,
    points: [
      { pseudonym: "C0001", time_ms: 1_750_000, is_self: false },
      { pseudonym: "C0002", time_ms: 1_790_000, is_self: false },
      { pseudonym: "C0003", time_ms: 1_800_000, is_self: true },
      { pseudonym: "C0004", time_ms: 1_870_000, is_self: false },
      { pseudonym: "C0005", time_ms: 1_910_000, is_self: false },
      { pseudonym: "C0006", time_ms: 1_950_000, is_self: false },
      { pseudonym: "C0007", time_ms: 2_010_000, is_self: false },
      { pseudonym: "C0008", time_ms: 2_080_000, is_self: false },
    ],
    curve: [
      { x_ms: 1_700_000, density: 0.0000001 },
      { x_ms: 1_800_000, density: 0.0000050 },
      { x_ms: 1_900_000, density: 0.0000065 },
      { x_ms: 2_000_000, density: 0.0000050 },
      { x_ms: 2_100_000, density: 0.0000010 },
    ],
    confidence: "high",
    ...overrides,
  };
}

export function mockAvailableRaceEvent(
  overrides?: Partial<AvailableRaceEvent>,
): AvailableRaceEvent {
  return {
    id: 100,
    name: "Válida IV — Cali",
    event_date: "2026-05-17",
    sequence_number: 4,
    location: "Cali",
    series_id: 1,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Handlers
// ---------------------------------------------------------------------------

export const athleteRaceAnalysisHandlers = [
  // GET /api/athletes/:id/race-analysis/insights
  http.get("*/api/athletes/:athleteId/race-analysis/insights", () => {
    const items: AthleteInsightOut[] = [
      mockInsight(),
      mockInsight({ id: 2, valida_num: 3, generated_at: "2026-04-20T10:00:00Z" }),
    ];
    const response: AthleteInsightListResponse = {
      items,
      total: items.length,
      limit: 50,
      offset: 0,
    };
    return HttpResponse.json(response);
  }),

  // GET /api/athletes/:id/race-analysis/insights/:insightId
  http.get(
    "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
    ({ params }) => {
      return HttpResponse.json(
        mockInsightDetail({ id: Number(params.insightId) }),
      );
    },
  ),

  // GET /api/athletes/:id/race-analysis/runs
  http.get("*/api/athletes/:athleteId/race-analysis/runs", () => {
    const items: AthleteRunOut[] = [mockRun()];
    const response: AthleteRunListResponse = {
      items,
      total: items.length,
      limit: 20,
      offset: 0,
    };
    return HttpResponse.json(response);
  }),

  // POST /api/athletes/:id/race-analysis/runs
  http.post("*/api/athletes/:athleteId/race-analysis/runs", () => {
    return HttpResponse.json(
      {
        run_id: "run-new-001",
        status: "running",
        started_at: "2026-05-22T10:00:00Z",
        status_url: "/api/race-analysis/runs/run-new-001/status",
        estimated_seconds: 45,
      },
      { status: 201 },
    );
  }),

  // GET /api/athletes/:id/race-analysis/distribution
  http.get("*/api/athletes/:athleteId/race-analysis/distribution", () => {
    return HttpResponse.json(mockDistribution());
  }),

  // GET /api/athletes/:id/race-analysis/evolution
  http.get("*/api/athletes/:athleteId/race-analysis/evolution", () => {
    return HttpResponse.json(mockEvolution());
  }),

  // GET /api/race-events/available-for-calendar
  http.get("*/api/race-events/available-for-calendar", () => {
    return HttpResponse.json([
      mockAvailableRaceEvent(),
      mockAvailableRaceEvent({ id: 101, sequence_number: 5, name: "Válida V" }),
    ]);
  }),
];

// Variantes para escenarios específicos
export const emptyInsightsHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights",
  () => {
    return HttpResponse.json({ items: [], total: 0, limit: 50, offset: 0 });
  },
);

/**
 * T027 (feature 036, US4) — listado con un único insight fallback
 * (`is_fallback=true`, id=77). Usado para probar el marcado visual, la
 * supresión del checkbox de boletín y la acción "Reintentar".
 */
export const fallbackInsightListHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights",
  () => {
    const items: AthleteInsightOut[] = [mockFallbackInsight()];
    const response: AthleteInsightListResponse = {
      items,
      total: items.length,
      limit: 50,
      offset: 0,
    };
    return HttpResponse.json(response);
  },
);

/** Detalle correspondiente a `fallbackInsightListHandler`. */
export const fallbackInsightDetailHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
  ({ params }) =>
    HttpResponse.json(
      mockFallbackInsightDetail({ id: Number(params.insightId) }),
    ),
);

export const lowConfidenceEvolutionHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/evolution",
  () => {
    return HttpResponse.json(
      mockEvolution({
        confidence: "low",
        series: [
          {
            valida_num: 1,
            event_id: 91,
            event_date: "2026-01-31",
            value: 120_000,
            unit: "ms",
            series_kind: "cup",
            label: "Válida I — Sevilla",
          },
        ],
      }),
    );
  },
);

export const emptyEvolutionHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/evolution",
  () => {
    return HttpResponse.json(
      mockEvolution({ series: [], confidence: "low" }),
    );
  },
);

/**
 * Handler T024 — colisión copa vs. campeonato.
 *
 * Dos puntos con el mismo valida_num=1 pero event_id distintos:
 *   - Copa Válida I  (event_id=91, series_kind="cup",          label="Válida I — Sevilla")
 *   - Campeonato Dep (event_id=200, series_kind="championship", label="Cto. Dep. — Ginebra")
 *
 * Los campos series_kind y label NO existen aún en el tipo EvolutionPoint
 * (T025 los añadirá). Se pasan como unknown para que el mock pueda usarlos
 * ya — los tests de T024 validan el comportamiento TARGET.
 *
 * NOTA PARA T025/T027: cuando se actualice EvolutionPoint, reemplazar el
 * cast `as unknown as EvolutionPoint` por el tipo correcto.
 */
export const cupAndChampionshipConflictHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/evolution",
  () => {
    const series: EvolutionResponse["series"] = [
      {
        valida_num: 1,
        event_id: 91,
        event_date: "2026-01-31",
        value: 120_000,
        unit: "ms",
        series_kind: "cup",
        label: "Válida I — Sevilla",
      },
      {
        valida_num: 1,
        event_id: 200,
        event_date: "2026-06-12",
        value: 98_000,
        unit: "ms",
        series_kind: "championship",
        label: "Cto. Dep. — Ginebra",
      },
    ];

    return HttpResponse.json(
      mockEvolution({
        confidence: "high",
        series,
      }),
    );
  },
);

/**
 * Handler T024 — DNF en campeonato.
 * Igual que cupAndChampionshipConflictHandler pero el campeonato tiene
 * value=null para probar que la lista DNF usa `label` en lugar de
 * romanForValida(valida_num).
 */
export const dnfChampionshipHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/evolution",
  () => {
    const series: EvolutionResponse["series"] = [
      {
        valida_num: 1,
        event_id: 91,
        event_date: "2026-01-31",
        value: 120_000,
        unit: "ms",
        series_kind: "cup",
        label: "Válida I — Sevilla",
      },
      {
        valida_num: 2,
        event_id: 92,
        event_date: "2026-02-28",
        value: 95_000,
        unit: "ms",
        series_kind: "cup",
        label: "Válida II — Ginebra",
      },
      {
        valida_num: 1,
        event_id: 200,
        event_date: "2026-06-12",
        value: null, // DNF en el campeonato
        unit: "ms",
        series_kind: "championship",
        label: "Cto. Dep. — Ginebra",
      },
    ];

    return HttpResponse.json(
      mockEvolution({
        confidence: "high",
        series,
      }),
    );
  },
);

export const lowConfidenceDistributionHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/distribution",
  () => {
    return HttpResponse.json(
      mockDistribution({
        confidence: "low",
        sample_size: 3,
        mean_ms: null,
        stddev_ms: null,
        athlete_z_score: null,
        athlete_percentile: null,
        curve: [],
        points: [
          { pseudonym: "C0001", time_ms: 1_750_000, is_self: false, display_name: null },
          { pseudonym: "C0002", time_ms: 1_800_000, is_self: true, display_name: null },
          { pseudonym: "C0003", time_ms: 1_870_000, is_self: false, display_name: null },
        ],
      }),
    );
  },
);

/** Handler para vista de entrenador: distribution con display_name poblado
 *  (coach/admin recibe nombres reales). */
export const coachDistributionHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/distribution",
  () => {
    return HttpResponse.json(
      mockDistribution({
        confidence: "low",
        sample_size: 3,
        mean_ms: null,
        stddev_ms: null,
        athlete_z_score: null,
        athlete_percentile: null,
        curve: [],
        points: [
          { pseudonym: "C0001", time_ms: 1_750_000, is_self: false, display_name: "Luciana Ríos" },
          { pseudonym: "C0002", time_ms: 1_800_000, is_self: true, display_name: "Diego Gómez" },
          { pseudonym: "C0003", time_ms: 1_870_000, is_self: false, display_name: "Sofía Martínez" },
        ],
      }),
    );
  },
);

/** Handler high-confidence con display_name para tests de reference lines de extremos. */
export const coachHighConfidenceDistributionHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/distribution",
  () => {
    return HttpResponse.json(
      mockDistribution({
        points: [
          { pseudonym: "C0001", time_ms: 1_750_000, is_self: false, display_name: "Luciana Ríos" },
          { pseudonym: "C0002", time_ms: 1_790_000, is_self: false, display_name: "Carlos Vera" },
          { pseudonym: "C0003", time_ms: 1_800_000, is_self: true, display_name: "Diego Gómez" },
          { pseudonym: "C0004", time_ms: 1_870_000, is_self: false, display_name: "Andrés Pino" },
          { pseudonym: "C0005", time_ms: 1_910_000, is_self: false, display_name: "Valentina Cruz" },
          { pseudonym: "C0006", time_ms: 1_950_000, is_self: false, display_name: "Mateo Soto" },
          { pseudonym: "C0007", time_ms: 2_010_000, is_self: false, display_name: "Isabela Rojas" },
          { pseudonym: "C0008", time_ms: 2_080_000, is_self: false, display_name: "Sofía Martínez" },
        ],
      }),
    );
  },
);

// ---------------------------------------------------------------------------
// Club insights by race handlers (Sprint 3)
// ---------------------------------------------------------------------------

/** Respuesta default: 3 items — coach ve todos, parent ve enmascarado. */
export const clubInsightsByRaceDefaultResponse: ClubInsightsByRaceResponse = {
  race_event_id: 4,
  race_event_label: "Válida 4 — Cali 17 may 2026",
  total_athletes: 3,
  items: [
    {
      athlete_id: 145,
      athlete_display_name: "Isabel Quiñoez",
      valida_num: 4,
      insight_id: 99,
      summary_excerpt: "Finalizó en 3er lugar, con progreso técnico en frenada.",
      generated_at: "2026-05-25T19:49:00",
      confidence: "medium",
    },
    {
      athlete_id: 0,
      athlete_display_name: "[Atleta del club]",
      valida_num: 4,
      insight_id: 100,
      summary_excerpt: null,
      generated_at: "2026-05-25T20:00:00",
      confidence: null,
    },
    {
      athlete_id: 201,
      athlete_display_name: "Mateo Pérez",
      valida_num: 4,
      insight_id: null,
      summary_excerpt: null,
      generated_at: null,
      confidence: null,
    },
  ],
};

export const clubInsightsByRaceHandler = http.get(
  "*/api/races/:raceEventId/club-insights",
  () => HttpResponse.json(clubInsightsByRaceDefaultResponse),
);

export const emptyClubInsightsByRaceHandler = http.get(
  "*/api/races/:raceEventId/club-insights",
  () =>
    HttpResponse.json({
      race_event_id: 4,
      race_event_label: "Válida 4 — Cali 17 may 2026",
      total_athletes: 0,
      items: [],
    } satisfies ClubInsightsByRaceResponse),
);

export const insightsWithSupersedesHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
  ({ params }) => {
    return HttpResponse.json(
      mockInsightDetail({
        id: Number(params.insightId),
        supersedes: [
          { id: 99, generated_at: "2026-05-10T10:00:00Z", coach_approved: true },
          { id: 98, generated_at: "2026-05-05T10:00:00Z", coach_approved: false },
        ],
      }),
    );
  },
);

// ---------------------------------------------------------------------------
// Season panorama (PR3) — GET /api/race-analysis/insights/season/{year}
// ---------------------------------------------------------------------------

export const seasonPanoramaDefaultResponse: SeasonPanoramaResponse = {
  season: 2026,
  total_athletes: 2,
  items: [
    {
      athlete_id: 144,
      athlete_display_name: "Juan Garcia",
      races_count: 2,
      wins: 1,
      podiums: 2,
      best_position: 1,
      total_points: 60,
    },
    {
      athlete_id: 145,
      athlete_display_name: "Maria Perez",
      races_count: 1,
      wins: 0,
      podiums: 0,
      best_position: 5,
      total_points: 10,
    },
  ],
};

export const seasonPanoramaHandler = http.get(
  "*/api/race-analysis/insights/season/:year",
  () => HttpResponse.json(seasonPanoramaDefaultResponse),
);

export const emptySeasonPanoramaHandler = http.get(
  "*/api/race-analysis/insights/season/:year",
  ({ params }) =>
    HttpResponse.json({
      season: Number(params.year),
      total_athletes: 0,
      items: [],
    } satisfies SeasonPanoramaResponse),
);

export const errorSeasonPanoramaHandler = http.get(
  "*/api/race-analysis/insights/season/:year",
  () => new HttpResponse(null, { status: 500 }),
);

// ---------------------------------------------------------------------------
// T017 — Races participation endpoint (US2)
// GET /api/athletes/:id/race-analysis/races?season=YYYY
// ---------------------------------------------------------------------------

/** Lista realista con una válida de copa y el campeonato departamental. */
export const mockRaceParticipationList = (
  overrides?: Partial<RaceParticipationResponse>,
): RaceParticipationResponse => ({
  season: 2026,
  items: [
    {
      event_id: 91,
      sequence_number: 1,
      series_kind: "cup",
      event_date: "2026-01-31",
      event_name: "Válida I Sevilla",
      location: "Sevilla",
      label: "Válida I — Sevilla",
    },
    {
      event_id: 200,
      sequence_number: 1,
      series_kind: "championship",
      event_date: "2026-06-12",
      event_name: "Campeonato Departamental",
      location: "Ginebra",
      label: "Cto. Dep. — Ginebra",
    },
  ],
  ...overrides,
});

/** Handler que devuelve una lista con dos carreras (copa + campeonato). */
export const racesListHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/races",
  () => HttpResponse.json(mockRaceParticipationList()),
);

/** Handler de cero carreras: athlete participó en la temporada pero
 *  ninguna carrera tiene datos aún (o no compitió ninguna). */
export const emptyRacesListHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/races",
  () =>
    HttpResponse.json(
      mockRaceParticipationList({ items: [] }) satisfies RaceParticipationResponse,
    ),
);

/** Handler de fallo — feature 036 (US5): antes de T035-follow-up esto caía
 *  en silencio al placeholder "Selecciona una carrera", sin avisar al coach
 *  que la petición de carreras falló. */
export const errorRacesListHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/races",
  () => new HttpResponse(null, { status: 500 }),
);

// ---------------------------------------------------------------------------
// T205 (feature 037) — POST /insights/:id/answer
// ---------------------------------------------------------------------------

/** Handler éxito: eco del body sobre un detalle base v3. */
export function answerInsightSuccessHandler(
  detailFactory: (overrides?: Partial<AthleteInsightDetailOut>) => AthleteInsightDetailOut,
) {
  return http.post(
    "*/api/athletes/:athleteId/race-analysis/insights/:insightId/answer",
    async ({ request }) => {
      const body = (await request.json()) as {
        answer_text?: string;
        rating?: number;
      };
      const now = new Date().toISOString();
      return HttpResponse.json(
        detailFactory({
          ...(body.answer_text !== undefined
            ? { coach_answer_text: body.answer_text, coach_answer_at: now }
            : {}),
          ...(body.rating !== undefined ? { coach_rating: body.rating } : {}),
        }),
      );
    },
  );
}

/** Handler 422 — ni `answer_text` ni `rating` en el body. */
export const answerInsightEmptyBodyHandler = http.post(
  "*/api/athletes/:athleteId/race-analysis/insights/:insightId/answer",
  () =>
    HttpResponse.json(
      { detail: "Debe enviar answer_text y/o rating." },
      { status: 422 },
    ),
);

/** Handler 403 — modo parent (RBAC denegado). */
export const answerInsightForbiddenHandler = http.post(
  "*/api/athletes/:athleteId/race-analysis/insights/:insightId/answer",
  () => HttpResponse.json({ detail: "No autorizado." }, { status: 403 }),
);
