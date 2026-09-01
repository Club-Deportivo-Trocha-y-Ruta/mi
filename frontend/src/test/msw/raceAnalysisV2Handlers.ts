/**
 * MSW handlers v2 — escenarios específicos del módulo race-analysis v2 (Task #9).
 *
 * - Endpoint nuevo: POST /api/athletes/{id}/race-analysis/season-summary
 * - Variantes de /insights para insights v2 (prompt_version=race_analyst_v2)
 *
 * Estos handlers NO se registran por default en setup.ts — se importan en
 * tests específicos vía ``mswServer.use(...)`` para no afectar suites legacy.
 */
import { http, HttpResponse } from "msw";

import {
  buildFiveDistinctV2Insights,
  mockInsightV2,
  mockInsightV2Detail,
  mockSeasonSummaryInsight,
} from "@/test/fixtures/insightV2";

// ---------------------------------------------------------------------------
// POST /season-summary — endpoint nuevo
// ---------------------------------------------------------------------------

const SEASON_SUMMARY_PATH =
  "*/api/athletes/:athleteId/race-analysis/season-summary";

function buildHandler(status: number, body: object) {
  return http.post(
    SEASON_SUMMARY_PATH,
    () => HttpResponse.json(body, { status }),
  );
}

/**
 * Handler éxito. Shape real (feature 036, T040): la llamada es SÍNCRONA,
 * sin run_id/status/started_at — ver `SeasonSummaryResponse` en
 * `api/athleteRaceAnalysis.ts`.
 */
export const seasonSummarySuccessHandler = buildHandler(200, {
  insight_id: 9001,
  season: 2026,
  summary_text: "Resumen de temporada de prueba con progreso técnico claro.",
  prompt_version: "race_analyst_v2",
  validas_analyzed: 4,
  generated_at: "2026-05-25T10:00:00Z",
});

/** Handler error 422 (menos de 3 válidas). */
export const seasonSummaryInsufficientValidasHandler = buildHandler(422, {
  detail: "Mínimo 3 válidas analizadas para generar el resumen.",
});

// ---------------------------------------------------------------------------
// GET /insights — listado con N insights v2 distintos
// ---------------------------------------------------------------------------

/** 5 insights v2 con summary_text DIFERENTE — verifica previews únicas. */
export const fiveDistinctV2InsightsHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights",
  () => {
    const items = buildFiveDistinctV2Insights();
    return HttpResponse.json({
      items,
      total: items.length,
      limit: 50,
      offset: 0,
    });
  },
);

/** Un solo insight v2. */
export const singleV2InsightHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights",
  () => {
    return HttpResponse.json({
      items: [mockInsightV2()],
      total: 1,
      limit: 50,
      offset: 0,
    });
  },
);

/** Insight v2 con valida_num=0 (season summary). */
export const seasonSummaryInsightInListHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights",
  () => {
    return HttpResponse.json({
      items: [mockSeasonSummaryInsight(), mockInsightV2()],
      total: 2,
      limit: 50,
      offset: 0,
    });
  },
);

// ---------------------------------------------------------------------------
// GET /insights/{id} — detalle v2
// ---------------------------------------------------------------------------

export const v2InsightDetailHandler = http.get(
  "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
  ({ params }) => {
    return HttpResponse.json(
      mockInsightV2Detail({ id: Number(params.insightId) }),
    );
  },
);
