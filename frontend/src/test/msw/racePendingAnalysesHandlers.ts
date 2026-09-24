/**
 * MSW handlers de los análisis IA pendientes del coach (feature 045, US5).
 *
 * Cubre:
 *   - GET  /api/race-analysis/pending-analyses?state=&season=
 *   - POST /api/race-analysis/runs/:runId/dismiss-stale
 *
 * Privacidad: los nombres de los fixtures son ficticios (Ley 1581).
 *
 * Uso:
 * ```ts
 * mswServer.use(...pendingAnalysesHandlers);
 * mswServer.use(pendingAnalysesErrorHandler); // sobreescribe puntualmente
 * ```
 */
import { http, HttpResponse } from "msw";

import type {
  PendingAnalysis,
  PendingAnalysisState,
} from "@/types/racePendingAnalyses.types";

const BASE = "*/api/race-analysis";

export function makePendingAnalysis(overrides?: Partial<PendingAnalysis>): PendingAnalysis {
  return {
    run_id: "run-stale-001",
    insight_id: 501,
    athlete_id: 144,
    athlete_ref: "Ana Ficticia",
    event_id: 7,
    event_label: "Copa Valle IV — Cali",
    season: 2026,
    kind: "valida",
    state: "stale",
    updated_at: "2026-09-20T15:30:00Z",
    ...overrides,
  };
}

/** Un resumen de temporada desactualizado: sin competencia, `kind="season_summary"`. */
export function makeSeasonSummaryPending(overrides?: Partial<PendingAnalysis>): PendingAnalysis {
  return makePendingAnalysis({
    run_id: "run-stale-season-001",
    insight_id: 601,
    athlete_id: 148,
    athlete_ref: "Eli Simulada",
    event_id: null,
    event_label: "Temporada 2025",
    season: 2025,
    kind: "season_summary",
    ...overrides,
  });
}

/** Un análisis por aprobar: sin insight persistido todavía (`insight_id: null`). */
export function makeAwaitingAnalysis(overrides?: Partial<PendingAnalysis>): PendingAnalysis {
  return makePendingAnalysis({
    run_id: "run-hitl-001",
    insight_id: null,
    athlete_id: 145,
    athlete_ref: "Beto Imaginario",
    event_id: 7,
    state: "awaiting_approval",
    ...overrides,
  });
}

export const defaultPendingByState: Record<PendingAnalysisState, PendingAnalysis[]> = {
  awaiting_approval: [
    makeAwaitingAnalysis(),
    makeAwaitingAnalysis({
      run_id: "run-hitl-002",
      athlete_id: 146,
      athlete_ref: "Cami Supuesta",
      event_id: null,
      event_label: "Temporada 2026",
      season: 2026,
      kind: "season_summary",
    }),
  ],
  stale: [
    makePendingAnalysis(),
    makePendingAnalysis({
      run_id: "run-stale-002",
      insight_id: 502,
      athlete_id: 147,
      athlete_ref: "Dani Inventado",
    }),
  ],
};

/** GET con la lista por defecto; refleja el `state` pedido (422 si falta o es desconocido). */
export const pendingAnalysesHandler = http.get(`${BASE}/pending-analyses`, ({ request }) => {
  const state = new URL(request.url).searchParams.get("state");
  if (state !== "awaiting_approval" && state !== "stale") {
    return HttpResponse.json({ detail: "state inválido" }, { status: 422 });
  }
  return HttpResponse.json(defaultPendingByState[state]);
});

export const pendingAnalysesEmptyHandler = http.get(`${BASE}/pending-analyses`, () =>
  HttpResponse.json([]),
);

export const pendingAnalysesErrorHandler = http.get(
  `${BASE}/pending-analyses`,
  () => new HttpResponse(null, { status: 500 }),
);

export const pendingAnalysesForbiddenHandler = http.get(`${BASE}/pending-analyses`, () =>
  HttpResponse.json({ detail: "No tienes permiso." }, { status: 403 }),
);

export const dismissStaleHandler = http.post(`${BASE}/runs/:runId/dismiss-stale`, ({ params }) =>
  HttpResponse.json({ run_id: String(params.runId), stale: false }),
);

/** 409: el run ya no está desactualizado (otro coach lo descartó o se re-ejecutó). */
export const dismissStaleConflictHandler = http.post(`${BASE}/runs/:runId/dismiss-stale`, () =>
  HttpResponse.json({ detail: "El análisis no está desactualizado" }, { status: 409 }),
);

export const pendingAnalysesHandlers = [pendingAnalysesHandler, dismissStaleHandler];
