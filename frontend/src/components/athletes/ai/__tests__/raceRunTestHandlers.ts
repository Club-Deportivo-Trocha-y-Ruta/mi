/**
 * Helpers MSW compartidos para pruebas que montan el árbol REAL de
 * `AnalysisRunTimeline` / `HITLApprovalCard` (feature 036, T011 y T015).
 *
 * No es un archivo de specs — sólo factories de handlers reutilizadas por
 * `AthleteAIAnalysisTab.test.tsx` y `AthleteAIAnalysisTab.stateIsolation.test.tsx`
 * para no duplicar los mismos fixtures de `/race-analysis/runs/:id/status`
 * y `/hitl/:step` en ambos archivos.
 */
import { http, HttpResponse } from "msw";

import type { RunStatusResponse } from "@/types/raceAnalysis.types";

/**
 * Responde SIEMPRE con el mismo `RunStatusResponse`, sin importar el
 * cursor `since` que mande el cliente. Suficiente para pruebas que sólo
 * necesitan que el timeline muestre UN estado estable — no ejercitan
 * transiciones de polling entre ticks.
 */
export function fixedRunStatusHandler(response: RunStatusResponse) {
  return http.get("*/api/race-analysis/runs/:runId/status", ({ params }) =>
    HttpResponse.json({ ...response, run_id: String(params.runId) }),
  );
}

/** Run pausado en `hitl_waiting`, con un evento `hitl_request` con
 * `step_id` + `draft_markdown` — lo mínimo que `AthleteAIAnalysisTab`
 * necesita para derivar `showHITL=true` y montar `HITLApprovalCard`. */
export function hitlWaitingRunStatusHandler(
  overrides?: Partial<RunStatusResponse>,
) {
  return fixedRunStatusHandler({
    run_id: "placeholder",
    state: "hitl_waiting",
    progress_pct: 70,
    current_node: "hitl_gate_review",
    started_at: "2026-08-20T10:00:00Z",
    estimated_seconds_remaining: 0,
    last_seq: 1,
    new_events: [
      {
        seq: 1,
        ts: "2026-08-20T10:00:01Z",
        type: "hitl_request",
        node: "hitl_gate_review",
        payload: {
          step_id: "hitl-step-1",
          draft_markdown: "### Borrador\nContenido de prueba.",
        },
      },
    ],
    ...overrides,
  });
}

/** Run ya en estado terminal `done` — para probar que `activeRunId` se
 * limpia al completar (T012). */
export function doneRunStatusHandler(overrides?: Partial<RunStatusResponse>) {
  return fixedRunStatusHandler({
    run_id: "placeholder",
    state: "done",
    progress_pct: 100,
    current_node: null,
    started_at: "2026-08-20T10:00:00Z",
    estimated_seconds_remaining: 0,
    last_seq: 1,
    new_events: [],
    ...overrides,
  });
}

/** GET /api/ai/status — presupuesto ok, sin restricciones. Requerido por
 * `LaunchAnalysisForm` real (`useAIStatus`) cuando NO está mockeado. */
export function aiStatusOkHandler() {
  return http.get("*/api/ai/status", () =>
    HttpResponse.json({
      budget_status: "ok",
      budget_remaining_pct: 90,
      concurrency_available: true,
      est_wait_seconds: 0,
    }),
  );
}

/** POST /api/race-analysis/runs/:runId/hitl/:stepId — acepta cualquier
 * decisión. */
export function hitlDecisionAcceptedHandler() {
  return http.post(
    "*/api/race-analysis/runs/:runId/hitl/:stepId",
    ({ params }) =>
      HttpResponse.json({
        accepted: true,
        run_id: String(params.runId),
        step_id: String(params.stepId),
        next_state: "running",
      }),
  );
}
