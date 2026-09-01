/**
 * E2E — feature 036, Wave 5 (T073): decisiones HITL "Rechazar" y "Editar".
 *
 * Motivación (spec.md, User Story 7): `AthleteAIAnalysisTab.test.tsx` mockea
 * `HITLApprovalCard` por completo y `HITLApprovalCard.test.tsx:38-49` solo
 * verifica que el botón "Editar" existe, sin hacer click. Ninguna suite hoy
 * dispara una decisión real y observa a dónde llega el run. Esta spec es la
 * única red para "Rechazar" y "Editar": los dos únicos caminos completos que
 * el approve feliz (T071, e2e/ai-insights-coach.spec.ts) no cubre.
 *
 * Cada test conduce la decisión hasta su ESTADO FINAL real (no solo el click
 * del botón):
 *   - Rechazar: la card HITL y el timeline desaparecen, y el histórico NO
 *     gana una fila nueva (el insight se persiste con `archived_at`, nunca
 *     visible — ver `persist_insight.py`).
 *   - Editar: la card y el timeline desaparecen, Y el histórico SÍ gana una
 *     fila nueva cuyo contenido es el markdown editado por el coach (no el
 *     borrador original del agente).
 *
 * Sin backend real — Playwright intercepta cada request con `page.route()`
 * usando predicados de URL (nunca globs: un glob también intercepta los
 * archivos fuente de Vite servidos por :5173 y rompe el montaje de React
 * con un error de MIME). Mismo idioma que el ya verificado
 * `e2e/cold-start.spec.ts`.
 *
 * Contrato real que este mock reproduce (`backend/app/routers/race_analysis.py`):
 *   - El estado terminal que ve el cliente tras CUALQUIER decisión (approve,
 *     reject o edit) es `"done"` — el backend mapea `rejected → RunState.DONE`
 *     ("ver result para distinguir"), así que un rechazo NUNCA se ve como
 *     "cancelado" o "con error" en el timeline del coach.
 *
 * Privacidad: todo nombre de atleta/coach en este archivo es sintético.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixtures — sintéticos, nunca nombres reales (Ley 1581)
// ---------------------------------------------------------------------------

const SEASON = new Date().getFullYear();

const TOKENS = {
  access_token: "e2e-hitl-access",
  refresh_token: "e2e-hitl-refresh",
  token_type: "bearer",
};

const COACH = {
  id: 601,
  email: "entrenador.hitl@trochyruta.com",
  first_name: "Coach",
  last_name: "Hitl",
  role: "coach",
  is_active: true,
  can_login: true,
  created_at: "2026-01-01T00:00:00Z",
};

const ATHLETE_ID = 4401;

const ATHLETE = {
  id: ATHLETE_ID,
  user_id: 9401,
  first_name: "Deportista",
  last_name: "PruebaHitl",
  birth_date: "2012-03-10",
  sex: "M",
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 13.5,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
  latest_anthropometry: null,
};

const RACE_EVENT_ID = 9201;

interface InsightFixture {
  id: number;
  season: number;
  valida_num: number | null;
  event_id: number | null;
  event_date: string | null;
  series_kind: "cup" | "championship" | null;
  use_case: string;
  summary_text: string;
  confidence: "low" | "medium" | "high";
  model: string;
  prompt_version: string;
  coach_approved: boolean;
  generated_at: string;
  approved_at: string | null;
  is_active: boolean;
  deprecated_at: string | null;
  is_fallback: boolean;
}

function existingInsight(id: number): InsightFixture {
  return {
    id,
    season: SEASON,
    valida_num: 3,
    event_id: 9100,
    event_date: `${SEASON}-02-01`,
    series_kind: "cup",
    use_case: "race_analysis",
    summary_text:
      "Resumen previo ya aprobado: mantuvo cadencia estable en el tramo de subida.",
    confidence: "medium",
    model: "gemini-3.1-flash-lite",
    prompt_version: "race_analyst_v1",
    coach_approved: true,
    generated_at: `${SEASON}-02-01T10:00:00Z`,
    approved_at: `${SEASON}-02-01T12:00:00Z`,
    is_active: true,
    deprecated_at: null,
    is_fallback: false,
  };
}

function editedInsight(id: number, text: string): InsightFixture {
  return {
    id,
    season: SEASON,
    valida_num: 1,
    event_id: RACE_EVENT_ID,
    event_date: `${SEASON}-03-02`,
    series_kind: "cup",
    use_case: "race_analysis",
    summary_text: text,
    confidence: "medium",
    model: "gemini-3.1-flash-lite",
    prompt_version: "race_analyst_v1",
    coach_approved: true,
    generated_at: new Date().toISOString(),
    approved_at: new Date().toISOString(),
    is_active: true,
    deprecated_at: null,
    is_fallback: false,
  };
}

// ---------------------------------------------------------------------------
// Helpers de red — idioma de e2e/cold-start.spec.ts (predicados de URL)
// ---------------------------------------------------------------------------

/** Solo peticiones al backend (:8000), nunca a los archivos fuente de Vite (:5173). */
function isBackend(url: URL): boolean {
  return url.port !== "5173";
}

async function setupAuthCoach(page: Page): Promise<void> {
  await page.addInitScript(
    ({ tokens, user }) => {
      sessionStorage.setItem(
        "auth-session",
        JSON.stringify({
          state: {
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            user,
            isAuthenticated: true,
          },
          version: 0,
        }),
      );
    },
    { tokens: TOKENS, user: COACH },
  );
}

/**
 * Mocks comunes a cualquier render del tab Análisis IA en modo coach,
 * independientes del escenario HITL bajo prueba (header ejecutivo,
 * Panorama con su sparkline, y el picker del formulario de lanzamiento).
 */
async function mockCommon(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/health",
    (route) => route.fulfill({ json: { ok: true } }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/auth/me",
    (route) => route.fulfill({ json: COACH }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/athletes/${ATHLETE_ID}`,
    (route) => route.fulfill({ json: ATHLETE }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${ATHLETE_ID}/anthropometry`,
    (route) => route.fulfill({ json: [] }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/ai/status",
    (route) =>
      route.fulfill({
        json: {
          budget_status: "ok",
          budget_remaining_pct: 80,
          concurrency_available: true,
          est_wait_seconds: 0,
        },
      }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${ATHLETE_ID}/race-analysis/evolution`,
    (route) =>
      route.fulfill({
        json: { season: SEASON, metric: "ranking", series: [], confidence: "low" },
      }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${ATHLETE_ID}/race-analysis/races`,
    (route) =>
      route.fulfill({
        json: {
          season: SEASON,
          items: [
            {
              event_id: RACE_EVENT_ID,
              sequence_number: 1,
              series_kind: "cup",
              event_date: `${SEASON}-03-02`,
              event_name: "Copa Valle I",
              location: "Cali",
              label: "Válida I · 2 mar",
            },
          ],
        },
      }),
  );
}

/** Registra `GET .../insights` devolviendo, en cada llamada, lo que retorne
 * `getPayload()` — permite que el test mute la lista tras la decisión HITL
 * y que el próximo refetch (disparado por `invalidateAthleteAiQueries`) la
 * refleje sin re-registrar la ruta. */
async function mockInsightsList(
  page: Page,
  getPayload: () => { items: InsightFixture[]; total: number },
): Promise<void> {
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${ATHLETE_ID}/race-analysis/insights`,
    (route) => {
      const payload = getPayload();
      return route.fulfill({
        json: { items: payload.items, total: payload.total, limit: 50, offset: 0 },
      });
    },
  );
}

async function gotoAiTab(page: Page): Promise<void> {
  await page.goto(`/athletes/${ATHLETE_ID}?tab=ai_analysis`);
  await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({
    timeout: 15_000,
  });
}

/** Lanza un análisis real desde el formulario (T096b "Revisión paso a paso"
 * + 1 carrera seleccionada) — nunca un atajo sintético que se salte la UI. */
async function launchAnalysis(page: Page): Promise<void> {
  await page.getByTestId("ai-subtab-launch").click();
  await expect(page.getByTestId("launch-analysis-form")).toBeVisible();
  await page.getByTestId("launch-explain-switch").check();
  await expect(page.getByTestId(`launch-event-${RACE_EVENT_ID}`)).toBeVisible({
    timeout: 10_000,
  });
  await page.getByTestId(`launch-event-${RACE_EVENT_ID}`).click();
  await page.getByTestId("launch-submit").click();
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Feature 036 — HITL: Rechazar y Editar (T073)", () => {
  test("HITL-REJECT: rechazar un draft limpia la card y el run, y NO agrega fila al histórico", async ({
    page,
  }) => {
    const RUN_ID = "run-e2e-hitl-reject-0001";
    const STEP_ID = "step-reject-1";
    const DRAFT_MARKDOWN =
      "Borrador del agente para revisión (E2E): mejoró el tiempo en el tramo técnico.";
    const PRE_EXISTING_ID = 8801;

    const insightItems: InsightFixture[] = [existingInsight(PRE_EXISTING_ID)];
    let decisionBody: Record<string, unknown> | null = null;

    await setupAuthCoach(page);
    await mockCommon(page);
    await mockInsightsList(page, () => ({
      items: insightItems,
      total: insightItems.length,
    }));

    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname === `/api/athletes/${ATHLETE_ID}/race-analysis/runs`,
      (route: Route) => {
        if (route.request().method() !== "POST") return route.fallback();
        return route.fulfill({
          json: {
            run_id: RUN_ID,
            status: "running",
            started_at: new Date().toISOString(),
            status_url: `/api/race-analysis/runs/${RUN_ID}/status`,
            estimated_seconds: 30,
          },
        });
      },
    );

    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname === `/api/race-analysis/runs/${RUN_ID}/status`,
      (route: Route) => {
        const since = Number(
          new URL(route.request().url()).searchParams.get("since") ?? "0",
        );
        const now = new Date().toISOString();
        if (decisionBody === null) {
          // Aún esperando que el coach decida — solo hay novedades en seq=1.
          if (since >= 1) return route.fulfill({ status: 304 });
          return route.fulfill({
            json: {
              run_id: RUN_ID,
              state: "hitl_waiting",
              progress_pct: 55,
              current_node: "hitl_gate_review",
              started_at: now,
              estimated_seconds_remaining: 15,
              new_events: [
                {
                  seq: 1,
                  ts: now,
                  type: "hitl_request",
                  node: "hitl_gate_review",
                  payload: { step_id: STEP_ID, draft_markdown: DRAFT_MARKDOWN },
                },
              ],
              last_seq: 1,
            },
          });
        }
        // Decisión ya recibida — el backend real mapea "rejected" a
        // RunState.DONE (race_analysis.py: "rejected": RunState.DONE).
        if (since >= 2) return route.fulfill({ status: 304 });
        return route.fulfill({
          json: {
            run_id: RUN_ID,
            state: "done",
            progress_pct: 100,
            current_node: null,
            started_at: now,
            estimated_seconds_remaining: 0,
            new_events: [
              {
                seq: 2,
                ts: now,
                type: "hitl_response",
                node: "hitl_gate_review",
                payload: { decision: "reject", step_id: STEP_ID },
              },
            ],
            last_seq: 2,
          },
        });
      },
    );

    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname === `/api/race-analysis/runs/${RUN_ID}/hitl/${STEP_ID}`,
      (route: Route) => {
        decisionBody = route.request().postDataJSON();
        return route.fulfill({
          json: {
            accepted: true,
            run_id: RUN_ID,
            step_id: STEP_ID,
            next_state: "running",
          },
        });
      },
    );

    await gotoAiTab(page);
    await launchAnalysis(page);

    // El lanzamiento cambia a Histórico y monta el timeline en vivo.
    await expect(page.getByTestId("analysis-run-timeline")).toBeVisible({
      timeout: 10_000,
    });
    const hitlCard = page.getByTestId("hitl-approval-card");
    await expect(hitlCard).toBeVisible({ timeout: 10_000 });
    await expect(hitlCard).toContainText(/mejoró el tiempo en el tramo técnico/i);

    // Decisión real: Rechazar, con motivo — no solo el click, todo el input.
    await page
      .getByTestId("hitl-reject-notes-input")
      .fill("Faltan datos suficientes para un análisis confiable (prueba E2E).");
    await page.getByTestId("hitl-reject-button").click();

    // Estado final real: la card Y el timeline desaparecen (activeRunId y
    // hitlStepId vuelven a null vía handleRunComplete al llegar a terminal).
    await expect(hitlCard).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByTestId("analysis-run-timeline")).toHaveCount(0, {
      timeout: 10_000,
    });

    // Petición real: decision=reject con las notas exactas escritas.
    expect(decisionBody).toMatchObject({
      decision: "reject",
      notes: "Faltan datos suficientes para un análisis confiable (prueba E2E).",
    });

    // Aserción central: el histórico sigue teniendo EXACTAMENTE la fila
    // preexistente — un rechazo nunca debe sumar una fila visible (el
    // insight persistido por el rechazo lleva `archived_at`, invisible para
    // el listado). No basta con "no está vacío": si el rechazo agregara una
    // segunda fila esta aserción de conteo la atraparía donde un mensaje de
    // "vacío" no lo haría.
    const cards = page.locator('[data-testid^="insight-card-"]');
    await expect(cards).toHaveCount(1);
    await expect(page.getByTestId(`insight-card-${PRE_EXISTING_ID}`)).toBeVisible();
  });

  test("HITL-EDIT: editar el borrador lo aprueba con el texto del coach, no el del agente", async ({
    page,
  }) => {
    const RUN_ID = "run-e2e-hitl-edit-0002";
    const STEP_ID = "step-edit-1";
    const NEW_INSIGHT_ID = 8802;
    const DRAFT_MARKDOWN =
      "Borrador original del agente (E2E): recomienda subir el volumen un 10%.";
    const EDITED_TEXT =
      "Edición del entrenador (E2E): mantener el volumen actual y reforzar técnica de frenada.";

    const insightItems: InsightFixture[] = [];
    let decisionBody: Record<string, unknown> | null = null;
    let decisionAccepted = false;

    await setupAuthCoach(page);
    await mockCommon(page);
    await mockInsightsList(page, () => ({
      items: insightItems,
      total: insightItems.length,
    }));

    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname === `/api/athletes/${ATHLETE_ID}/race-analysis/runs`,
      (route: Route) => {
        if (route.request().method() !== "POST") return route.fallback();
        return route.fulfill({
          json: {
            run_id: RUN_ID,
            status: "running",
            started_at: new Date().toISOString(),
            status_url: `/api/race-analysis/runs/${RUN_ID}/status`,
            estimated_seconds: 30,
          },
        });
      },
    );

    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname === `/api/race-analysis/runs/${RUN_ID}/status`,
      (route: Route) => {
        const since = Number(
          new URL(route.request().url()).searchParams.get("since") ?? "0",
        );
        const now = new Date().toISOString();
        if (!decisionAccepted) {
          if (since >= 1) return route.fulfill({ status: 304 });
          return route.fulfill({
            json: {
              run_id: RUN_ID,
              state: "hitl_waiting",
              progress_pct: 55,
              current_node: "hitl_gate_review",
              started_at: now,
              estimated_seconds_remaining: 15,
              new_events: [
                {
                  seq: 1,
                  ts: now,
                  type: "hitl_request",
                  node: "hitl_gate_review",
                  payload: { step_id: STEP_ID, draft_markdown: DRAFT_MARKDOWN },
                },
              ],
              last_seq: 1,
            },
          });
        }
        if (since >= 2) return route.fulfill({ status: 304 });
        return route.fulfill({
          json: {
            run_id: RUN_ID,
            state: "done",
            progress_pct: 100,
            current_node: null,
            started_at: now,
            estimated_seconds_remaining: 0,
            new_events: [
              {
                seq: 2,
                ts: now,
                type: "hitl_response",
                node: "hitl_gate_review",
                payload: { decision: "edit", step_id: STEP_ID, has_edits: true },
              },
            ],
            last_seq: 2,
          },
        });
      },
    );

    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname === `/api/race-analysis/runs/${RUN_ID}/hitl/${STEP_ID}`,
      (route: Route) => {
        decisionBody = route.request().postDataJSON();
        decisionAccepted = true;
        // El backend real persiste `persist_insight` durante la reanudación
        // post-HITL (BUG-002 fix, ver comentario en el router) — acá se
        // simula ese efecto: la fila nueva queda disponible para el
        // próximo refetch de `athlete-insights` (que dispara
        // `useApproveStep.onSuccess` al invalidar).
        insightItems.push(editedInsight(NEW_INSIGHT_ID, EDITED_TEXT));
        return route.fulfill({
          json: {
            accepted: true,
            run_id: RUN_ID,
            step_id: STEP_ID,
            next_state: "running",
          },
        });
      },
    );

    await gotoAiTab(page);
    await launchAnalysis(page);

    await expect(page.getByTestId("analysis-run-timeline")).toBeVisible({
      timeout: 10_000,
    });
    const hitlCard = page.getByTestId("hitl-approval-card");
    await expect(hitlCard).toBeVisible({ timeout: 10_000 });
    await expect(hitlCard).toContainText(/subir el volumen un 10%/i);

    // Decisión real: Editar — abre el dialog, reemplaza el markdown y
    // confirma. No un click sintético: se escribe el texto real.
    await page.getByTestId("hitl-edit-button").click();
    const textarea = page.getByTestId("hitl-edit-textarea");
    await expect(textarea).toBeVisible({ timeout: 10_000 });
    await expect(textarea).toHaveValue(DRAFT_MARKDOWN);
    await textarea.fill(EDITED_TEXT);
    // La vista previa en vivo (mismo `MarkdownReportViewer`, sin red de por
    // medio) confirma que el estado editado es el que se va a enviar.
    await expect(page.getByTestId("hitl-edit-save-button")).toBeVisible();
    await page.getByTestId("hitl-edit-save-button").click();

    // Petición real: decision=edit con el texto EXACTO escrito por el coach,
    // nunca el borrador original del agente.
    await expect
      .poll(() => decisionBody, { timeout: 10_000 })
      .toMatchObject({ decision: "edit", edits: EDITED_TEXT });

    // El dialog se cierra solo (handleSaveEdit → setEditOpen(false) si no
    // hubo error) y la card/timeline llegan a su estado terminal real.
    await expect(textarea).toHaveCount(0, { timeout: 10_000 });
    await expect(hitlCard).toHaveCount(0, { timeout: 10_000 });
    await expect(page.getByTestId("analysis-run-timeline")).toHaveCount(0, {
      timeout: 10_000,
    });

    // Aserción central: el histórico gana una fila NUEVA cuyo contenido es
    // el texto editado por el coach — no el borrador del agente, y no un
    // "editar aprobado sin más" genérico.
    const newCard = page.getByTestId(`insight-card-${NEW_INSIGHT_ID}`);
    await expect(newCard).toBeVisible({ timeout: 10_000 });
    await expect(newCard).toContainText(/mantener el volumen actual/i);
    await expect(page.getByText(DRAFT_MARKDOWN)).toHaveCount(0);
  });
});
