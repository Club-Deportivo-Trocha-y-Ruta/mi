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

/**
 * Responde HONRANDO el cursor `since`, como hace el backend real
 * (`GET /runs/{id}/status?since=N` devuelve sólo los eventos con
 * `seq > N`).
 *
 * `fixedRunStatusHandler` reenvía siempre el set completo, así que
 * cualquier consumidor que pierda su buffer local de eventos sigue
 * "funcionando" en tests y falla en producción: en cuanto el cursor
 * alcanza `last_seq`, el backend real deja de reenviar el
 * `hitl_request` que lleva el `draft_markdown`.
 */
export function cursorAwareRunStatusHandler(response: RunStatusResponse) {
  return http.get("*/api/race-analysis/runs/:runId/status", ({ params, request }) => {
    const since = Number(new URL(request.url).searchParams.get("since") ?? 0);
    return HttpResponse.json({
      ...response,
      run_id: String(params.runId),
      new_events: (response.new_events ?? []).filter((e) => e.seq > since),
    });
  });
}

/**
 * Emite los eventos de forma PROGRESIVA: cada request devuelve como mucho
 * `batchSize` eventos con `seq > since`, imitando un run que avanza a lo
 * largo de varios polls.
 *
 * Es la única forma de destapar el reparto del stream entre observadores:
 * con un set estático todos reciben todo en su primer poll y nunca
 * divergen.
 */
export function progressiveRunStatusHandler(
  allEvents: RunStatusResponse["new_events"],
  base: Omit<RunStatusResponse, "new_events" | "last_seq">,
  batchSize = 2,
) {
  const maxSeq = allEvents.reduce((m, e) => Math.max(m, e.seq), 0);
  return http.get("*/api/race-analysis/runs/:runId/status", ({ params, request }) => {
    const since = Number(new URL(request.url).searchParams.get("since") ?? 0);
    const pending = allEvents.filter((e) => e.seq > since).slice(0, batchSize);
    return HttpResponse.json({
      ...base,
      run_id: String(params.runId),
      new_events: pending,
      last_seq: pending.length ? pending[pending.length - 1].seq : Math.min(since, maxSeq),
    });
  });
}

/**
 * Simula el estado degradado que se ve en producción: el run está en
 * `hitl_waiting` pero el cliente arrastra un cursor ya pasado, así que el
 * backend (que sólo reenvía `seq > since`) no vuelve a mandar el
 * `hitl_request` con el borrador.
 *
 * La PRIMERA request responde con `new_events: []` y un `last_seq` ya
 * avanzado —el cliente queda sin el evento—; a partir de ahí se comporta
 * como el backend real. Sólo un refetch con el cursor reiniciado a 0
 * recupera el borrador.
 */
export function staleCursorHitlHandler(
  event: RunStatusResponse["new_events"][number],
  base: Omit<RunStatusResponse, "new_events" | "last_seq">,
) {
  let firstCall = true;
  return http.get("*/api/race-analysis/runs/:runId/status", ({ params, request }) => {
    const since = Number(new URL(request.url).searchParams.get("since") ?? 0);
    const body = { ...base, run_id: String(params.runId), last_seq: event.seq };
    if (firstCall) {
      firstCall = false;
      return HttpResponse.json({ ...body, new_events: [] });
    }
    return HttpResponse.json({
      ...body,
      new_events: event.seq > since ? [event] : [],
    });
  });
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
