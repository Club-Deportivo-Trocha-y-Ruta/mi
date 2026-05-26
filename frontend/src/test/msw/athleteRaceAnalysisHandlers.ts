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
  return {
    id: 1,
    season: 2026,
    valida_num: 4,
    event_id: 100,
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
    ...overrides,
  };
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
      },
      {
        valida_num: 2,
        event_id: 92,
        event_date: "2026-02-28",
        value: 95_000,
        unit: "ms",
      },
      {
        valida_num: 3,
        event_id: 93,
        event_date: "2026-04-19",
        value: 60_000,
        unit: "ms",
      },
      {
        valida_num: 4,
        event_id: 94,
        event_date: "2026-05-17",
        value: 45_000,
        unit: "ms",
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
    valida_num: 4,
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
