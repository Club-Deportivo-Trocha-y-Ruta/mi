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
export const seasonSummarySuccessHandler = buildHandler(202, {
  run_id: "run-season-9001",
  status: "queued",
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

// ---------------------------------------------------------------------------
// T205 (feature 037) — POST /season-summary, contrato v3 asíncrono
// (202 {run_id, status}, ver AthleteSeasonSummaryRunResponse). Reemplaza
// el shape síncrono legacy (SEASON_SUMMARY_PATH arriba) una vez T203
// migre el backend.
// ---------------------------------------------------------------------------

/** Handler éxito v3: lanza un run agéntico de season summary. */
export const seasonSummaryRunSuccessHandler = http.post(
  SEASON_SUMMARY_PATH,
  () =>
    HttpResponse.json(
      { run_id: "run-season-fake-0001", status: "running" },
      { status: 202 },
    ),
);

/** Handler 451 — consentimiento IA no otorgado (T203). */
export const seasonSummaryConsentMissingHandler = http.post(
  SEASON_SUMMARY_PATH,
  () =>
    HttpResponse.json(
      { detail: "Consentimiento de IA requerido." },
      { status: 451 },
    ),
);

// ---------------------------------------------------------------------------
// T302 (feature 037) — POST /chat, usado por `AthleteAnalystChatPanel`
// (scope por `athlete_id`) y `CompetitionChatPanel` (scope por
// `race_event_id`), ambos vía `useChatSession`.
// ---------------------------------------------------------------------------

const CHAT_PATH = "*/api/race-analysis/chat";

/** Handler éxito — responde con una respuesta fija, sin citas ni tools. */
export const chatTurnSuccessHandler = http.post(CHAT_PATH, () =>
  HttpResponse.json({
    answer: "Respuesta simulada del analista.",
    citations_used: [],
    tools_called: [],
  }),
);

/** Handler 503 — IA deshabilitada. */
export const chatTurnUnavailableHandler = http.post(CHAT_PATH, () =>
  HttpResponse.json({ detail: "IA no disponible." }, { status: 503 }),
);
