/**
 * E2E — coach flows for the athlete AI insights tab (feature 036, Wave 5 /
 * US7, tasks T070/T071/T075).
 *
 * Self-contained, no backend/docker required: auth + every API response are
 * mocked via `page.route`, mirroring `cold-start.spec.ts` and
 * `target-size.spec.ts` — the persisted Zustand `auth-session` shape is
 * written directly into `sessionStorage` (`addInitScript`, skips the real
 * login round-trip), and every backend route is matched by URL PREDICATE,
 * never a glob string, so Vite's own dev-server module requests (port 5173)
 * are never swallowed (e.g. `src/api/athletes.ts` shares path segments with
 * the real `/api/athletes` route).
 *
 * Three tests, three synthetic athletes (fake names, no real minor — Ley
 * 1581), each isolated so a failure in one can't cascade into another:
 *
 *   T070 — Camila Restrepo (id 701): coach happy path. Enter the tab, see
 *          Panorama with its KPIs, visit each of the five sub-tabs, open
 *          and close the comparator sheet.
 *   T071 — Valeria Ospina (id 703): the module's central business flow,
 *          which had NO e2e coverage before this file — launch an analysis,
 *          watch the run timeline progress, approve the HITL gate, and
 *          confirm the newly-created insight appears in the history. The
 *          run-status polling sequence (`GET .../runs/:id/status`) is
 *          mocked in three phases (running → hitl_waiting → done): each
 *          phase re-registers the SAME route pattern, and Playwright always
 *          dispatches to the most-recently-registered matching handler, so
 *          re-registering acts as an override for every following poll
 *          without needing to model the `since` cursor.
 *   T075 — Camila Restrepo (701) then Nicolás Duarte (702): the US3
 *          regression at the outermost level. Selects a newsletter checkbox
 *          on Camila's history (populating `newsletterSelection`), then
 *          drives a SAME-ROUTE transition to Nicolás's profile — never a
 *          second `page.goto()` (a real document reload, which would
 *          trivially "fix" the bug by remounting everything), and, per a
 *          finding made while writing this test, deliberately not "click
 *          Volver a lista, then click the other athlete's row" either: the
 *          Atletas list is a DIFFERENT route (`AthletesListPage`), so going
 *          through it unmounts `AthleteDetailPage` itself first, which
 *          masks the bug entirely (verified: with `key={athlete.id}`
 *          removed, that path still passed). `AthleteDetailPage` renders at
 *          `/athletes/:id`, a route React Router reuses across a param-only
 *          change — there is, today, no in-app `<Link>` that goes directly
 *          from one athlete's page to another's, so the test reproduces that
 *          exact transition via `history.pushState` + a manually dispatched
 *          `popstate` (the event `BrowserRouter` itself listens for — both
 *          genuine DOM/browser APIs, no app internals reached into). Without
 *          `key={athlete.id}` on the `AthleteAIAnalysisTab` mount
 *          (`AthleteDetailPage.tsx`), React reuses the same component
 *          instance across that transition and its internal `useState`
 *          (sub-tab, newsletter selection) survives the athlete switch.
 *
 * Run just this file: `cd frontend && npx playwright test e2e/ai-insights-coach.spec.ts`
 */
import { test, expect, type Page, type Route } from "@playwright/test";

const WAIT_TIMEOUT = 15_000;

/** Current calendar year — fixtures use it for `season`/`event_date` so
 * this file never rots the way a hardcoded past year would (see
 * `target-size.spec.ts`'s Wave 5 repair note on stale fixture dates). */
const SEASON = new Date().getFullYear();

// ---------------------------------------------------------------------------
// Auth — mirrors target-size.spec.ts / dashboard-coach.spec.ts: write the
// persisted Zustand `auth-session` shape directly into sessionStorage so no
// real login round-trip is needed.
// ---------------------------------------------------------------------------

const COACH_USER = {
  id: 1,
  email: "entrenador@trochyruta.com",
  first_name: "Juan",
  last_name: "Diaz",
  phone: null,
  role: "coach",
  is_active: true,
  can_login: true,
  club_ids: [1],
  created_at: "2026-01-01T00:00:00Z",
};

const TOKENS = {
  access_token: "e2e-ai-insights-coach-access",
  refresh_token: "e2e-ai-insights-coach-refresh",
};

async function setupAuth(page: Page): Promise<void> {
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
            isLoading: false,
          },
          version: 0,
        }),
      );
    },
    { tokens: TOKENS, user: COACH_USER },
  );
}

// ---------------------------------------------------------------------------
// Backend mocking — URL predicates only (see header comment).
// ---------------------------------------------------------------------------

const isBackend = (url: URL) => url.port !== "5173";

function jsonRoute(body: unknown, status = 200) {
  return (route: Route) => route.fulfill({ status, json: body });
}

async function mockHealth(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/health",
    jsonRoute({ ok: true }),
  );
}

/** `LinkedParentsCard` renders unconditionally on `AthleteDetailPage`
 * (above the tab strip, regardless of which tab is active) — query-param
 * based (`?athlete_id=`), so one path-only registration covers every
 * athlete in this file. */
async function mockLinkedParents(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/parent-athletes",
    jsonRoute({ items: [] }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/parent-athletes/invites",
    jsonRoute([]),
  );
}

// ---------------------------------------------------------------------------
// Athlete fixtures — three synthetic (fake) athletes, never a real minor.
// ---------------------------------------------------------------------------

interface AthleteFixture {
  id: number;
  first_name: string;
  last_name: string;
}

const ATHLETE_A: AthleteFixture = { id: 701, first_name: "Camila", last_name: "Restrepo" };
const ATHLETE_B: AthleteFixture = { id: 702, first_name: "Nicolás", last_name: "Duarte" };
const ATHLETE_C: AthleteFixture = { id: 703, first_name: "Valeria", last_name: "Ospina" };

function athleteDetail(a: AthleteFixture) {
  return {
    id: a.id,
    user_id: a.id + 1000,
    first_name: a.first_name,
    last_name: a.last_name,
    birth_date: "2012-01-15",
    sex: "F",
    club_join_date: "2024-01-01",
    years_in_club: 2,
    age_decimal: 14.3,
    category: "Sub-15",
    club_id: 1,
    created_at: "2024-01-01T00:00:00Z",
    latest_anthropometry: null,
  };
}

/** Mocks the page shell every `/athletes/:id` route needs, regardless of
 * which tab ends up active: the athlete itself + its anthropometry list. */
async function mockAthleteShell(page: Page, a: AthleteFixture): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/athletes/${a.id}`,
    jsonRoute(athleteDetail(a)),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/athletes/${a.id}/anthropometry`,
    jsonRoute([]),
  );
}

// ---------------------------------------------------------------------------
// AI-tab fixtures — insights / evolution / races / distribution / ai-status.
// ---------------------------------------------------------------------------

interface InsightOverrides {
  id: number;
  valida_num: number;
  event_id: number | null;
  event_date: string | null;
  generated_at: string;
}

function makeInsight(o: InsightOverrides) {
  return {
    id: o.id,
    season: SEASON,
    valida_num: o.valida_num,
    event_id: o.event_id,
    event_date: o.event_date,
    series_kind: o.event_id !== null ? "cup" : null,
    use_case: "race_analysis_v2",
    summary_text:
      "## Qué pasó\nBuena carrera, sostuvo el ritmo toda la prueba.\n## Qué sigue\nMantener el volumen de entrenamiento.",
    confidence: "high",
    model: "gemini-3.1-flash-lite",
    prompt_version: "race_analyst_v2",
    coach_approved: true,
    generated_at: o.generated_at,
    approved_at: o.generated_at,
    is_active: true,
    deprecated_at: null,
    is_fallback: false,
  };
}

function insightDetail(base: ReturnType<typeof makeInsight>) {
  return {
    ...base,
    recommendations: [] as unknown[],
    metrics_snapshot: {},
    principles_cited: [] as unknown[],
    supersedes: [] as unknown[],
    superseded_by: null,
  };
}

interface RaceFixture {
  event_id: number;
  sequence_number: number;
  event_date: string;
  event_name: string;
  location: string;
}

function raceItem(r: RaceFixture) {
  return {
    event_id: r.event_id,
    sequence_number: r.sequence_number,
    series_kind: "cup" as const,
    event_date: r.event_date,
    event_name: r.event_name,
    location: r.location,
    label: `Válida ${r.sequence_number} · ${r.event_date.slice(8, 10)}/${r.event_date.slice(5, 7)}`,
  };
}

const AI_STATUS_OK = {
  budget_status: "ok",
  budget_remaining_pct: 80,
  concurrency_available: true,
  est_wait_seconds: 0,
};

/**
 * Registers every endpoint `/athletes/:id?tab=ai_analysis` touches across
 * its five sub-tabs. Path-only matching (query params ignored) means one
 * route per endpoint covers every param variant each sub-tab requests it
 * with — same convention as `target-size.spec.ts`'s `mockAthleteAiTabApi`.
 *
 * `insights` is a live array reference (not a snapshot): T071 mutates it
 * in place between the launch and the HITL approval so the SAME registered
 * route reflects the "before" and "after" list without a second
 * `page.route()` call.
 */
function mockAthleteAiEndpoints(
  page: Page,
  athleteId: number,
  data: {
    insights: ReturnType<typeof makeInsight>[];
    races: RaceFixture[];
    evolutionSeries?: Array<{
      valida_num: number;
      event_id: number;
      event_date: string;
      value: number;
      label: string;
    }>;
    distribution?: unknown;
  },
): Promise<void[]> {
  const base = `/api/athletes/${athleteId}/race-analysis`;
  return Promise.all([
    page.route(
      (url) => isBackend(url) && url.pathname === `${base}/insights`,
      (route) =>
        route.fulfill({
          status: 200,
          json: {
            items: [...data.insights].sort((x, y) =>
              (y.event_date ?? "").localeCompare(x.event_date ?? ""),
            ),
            total: data.insights.length,
            limit: 50,
            offset: 0,
          },
        }),
    ),
    page.route(
      (url) =>
        isBackend(url) && new RegExp(`^${base}/insights/\\d+$`).test(url.pathname),
      (route: Route) => {
        const id = Number(new URL(route.request().url()).pathname.split("/").pop());
        const found = data.insights.find((i) => i.id === id);
        if (!found) {
          route.fulfill({ status: 404, json: { detail: "not found" } });
          return;
        }
        route.fulfill({ status: 200, json: insightDetail(found) });
      },
    ),
    page.route(
      (url) => isBackend(url) && url.pathname === `${base}/evolution`,
      jsonRoute({
        season: SEASON,
        metric: "ranking",
        series: (data.evolutionSeries ?? []).map((p) => ({
          valida_num: p.valida_num,
          event_id: p.event_id,
          event_date: p.event_date,
          value: p.value,
          unit: "posición",
          series_kind: "cup",
          label: p.label,
        })),
        confidence: "high",
      }),
    ),
    page.route(
      (url) => isBackend(url) && url.pathname === `${base}/races`,
      jsonRoute({ season: SEASON, items: data.races.map(raceItem) }),
    ),
    page.route(
      (url) => isBackend(url) && url.pathname === `${base}/distribution`,
      data.distribution
        ? jsonRoute(data.distribution)
        : (route) => route.fulfill({ status: 404, json: { detail: "sin datos" } }),
    ),
    page.route(
      (url) => isBackend(url) && url.pathname === "/api/ai/status",
      jsonRoute(AI_STATUS_OK),
    ),
  ]);
}

/** Navigates straight to the AI tab and waits for real data (not the
 * loading Skeleton) — tolerates the Suspense fallback the lazy-loaded tab
 * renders first (T096, feature 036). */
async function gotoAthleteAiTab(page: Page, athleteId: number): Promise<void> {
  await page.goto(`/athletes/${athleteId}?tab=ai_analysis`);
  await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
  await expect(page.getByTestId("ai-header-summary")).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
}

/**
 * Drives a SAME-ROUTE, in-app transition to `path` — used only by T075,
 * where a real second `page.goto()` (a full document reload) would
 * trivially "fix" the US3 regression by remounting literally everything,
 * hiding the very bug the test exists to catch.
 *
 * There is no in-app `<Link>` today that goes directly from one athlete's
 * `/athletes/:id` to another's (every real path detours through the
 * Atletas list, a DIFFERENT route that unmounts `AthleteDetailPage` on its
 * own — verified empirically while writing this test). So this reproduces
 * the transition through React Router's own production `popstate` handling
 * instead: `history.pushState` changes the URL, and `BrowserRouter`
 * (subscribed to `popstate`, since `pushState` itself fires no native
 * event) only reacts once that event is dispatched. Both are genuine
 * browser/DOM APIs — nothing app-specific is reached into.
 */
async function spaNavigate(page: Page, path: string): Promise<void> {
  await page.evaluate((url) => {
    window.history.pushState({}, "", url);
    window.dispatchEvent(new PopStateEvent("popstate"));
  }, path);
}

test.beforeEach(async ({ page }) => {
  await setupAuth(page);
  await mockHealth(page);
  await mockLinkedParents(page);
});

// ---------------------------------------------------------------------------
// T070 — coach happy path
// ---------------------------------------------------------------------------

test("T070: coach happy path — Panorama KPIs, all five sub-tabs, comparator sheet open/close", async ({
  page,
}) => {
  const EVENT_1 = 71001; // Válida I
  const EVENT_2 = 71002; // Válida II (más reciente)
  const INSIGHT_1 = makeInsight({
    id: 91001,
    valida_num: 1,
    event_id: EVENT_1,
    event_date: `${SEASON}-02-08`,
    generated_at: `${SEASON}-02-09T10:00:00Z`,
  });
  const INSIGHT_2 = makeInsight({
    id: 91002,
    valida_num: 2,
    event_id: EVENT_2,
    event_date: `${SEASON}-04-12`,
    generated_at: `${SEASON}-04-13T10:00:00Z`,
  });
  const races: RaceFixture[] = [
    { event_id: EVENT_1, sequence_number: 1, event_date: `${SEASON}-02-08`, event_name: "Copa Valle I", location: "Cali" },
    { event_id: EVENT_2, sequence_number: 2, event_date: `${SEASON}-04-12`, event_name: "Copa Valle II", location: "Palmira" },
  ];

  await mockAthleteShell(page, ATHLETE_A);
  await mockAthleteAiEndpoints(page, ATHLETE_A.id, {
    insights: [INSIGHT_1, INSIGHT_2],
    races,
    evolutionSeries: [
      { valida_num: 1, event_id: EVENT_1, event_date: `${SEASON}-02-08`, value: 3, label: "Válida I" },
      { valida_num: 2, event_id: EVENT_2, event_date: `${SEASON}-04-12`, value: 1, label: "Válida II" },
    ],
    distribution: {
      season: SEASON,
      event_id: EVENT_2,
      category_id: 1,
      category_code: "INF_F",
      sample_size: 6,
      mean_ms: 3_600_000,
      stddev_ms: 100_000,
      athlete_time_ms: 3_500_000,
      athlete_z_score: -1,
      athlete_percentile: 82,
      points: [{ pseudonym: "C0001", time_ms: 3_500_000, is_self: true, display_name: "Camila Restrepo" }],
      curve: [{ x_ms: 3_500_000, density: 0.2 }],
      confidence: "high",
    },
  });

  await gotoAthleteAiTab(page, ATHLETE_A.id);

  // --- Panorama (default sub-tab) with its KPIs ---------------------------
  await expect(page.getByTestId("panorama-view")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("hero-last-insight-card")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("panorama-kpi-total")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("panorama-kpi-total")).toContainText("2");
  await expect(page.getByTestId("panorama-kpi-best-position")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("panorama-kpi-races")).toBeVisible({ timeout: WAIT_TIMEOUT });

  // --- Histórico ------------------------------------------------------------
  await page.getByTestId("ai-subtab-history").click();
  await expect(page.getByTestId(`insight-card-${INSIGHT_2.id}`)).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId(`insight-card-${INSIGHT_1.id}`)).toBeVisible({ timeout: WAIT_TIMEOUT });

  // --- Evolución --------------------------------------------------------------
  await page.getByTestId("ai-subtab-evolution").click();
  await expect(page.getByTestId("evolution-chart")).toBeVisible({ timeout: WAIT_TIMEOUT });

  // --- Distribución + comparador (Sheet) — open then close -------------------
  await page.getByTestId("ai-subtab-distribution").click();
  await expect(page.getByTestId("distribution-chart")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("open-comparator-sheet")).toBeVisible({ timeout: WAIT_TIMEOUT });

  await page.getByTestId("open-comparator-sheet").click();
  await expect(page.getByTestId("comparator-panel")).toBeVisible({ timeout: WAIT_TIMEOUT });
  // Fullest state of the Sheet — both sides of the default válida pair loaded.
  await expect(page.getByTestId("comparator-diff-table")).toBeVisible({ timeout: WAIT_TIMEOUT });

  await page.getByRole("button", { name: "Cerrar panel" }).click();
  await expect(page.getByTestId("comparator-panel")).not.toBeVisible({ timeout: WAIT_TIMEOUT });

  // --- Analizar con IA ---------------------------------------------------------
  await page.getByTestId("ai-subtab-launch").click();
  await expect(page.getByTestId("launch-analysis-form")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId(`launch-event-${EVENT_2}`)).toBeVisible({ timeout: WAIT_TIMEOUT });
});

// ---------------------------------------------------------------------------
// T071 — launch -> run timeline -> HITL card -> approve -> new insight
// ---------------------------------------------------------------------------

test("T071: launch an analysis, approve the HITL gate, and the new insight appears in history", async ({
  page,
}) => {
  const EVENT_1 = 73001; // Válida I — ya analizada
  const EVENT_2 = 73002; // Válida II — la que se va a lanzar
  const EXISTING_INSIGHT = makeInsight({
    id: 93001,
    valida_num: 1,
    event_id: EVENT_1,
    event_date: `${SEASON}-02-01`,
    generated_at: `${SEASON}-02-02T10:00:00Z`,
  });
  const NEW_INSIGHT = makeInsight({
    id: 93002,
    valida_num: 2,
    event_id: EVENT_2,
    event_date: `${SEASON}-04-20`,
    generated_at: new Date().toISOString(),
  });
  const races: RaceFixture[] = [
    { event_id: EVENT_1, sequence_number: 1, event_date: `${SEASON}-02-01`, event_name: "Copa Valle I", location: "Cali" },
    { event_id: EVENT_2, sequence_number: 2, event_date: `${SEASON}-04-20`, event_name: "Copa Valle II", location: "Palmira" },
  ];
  // Mutated in place once the HITL step is approved (see below) — the
  // `insights` route registered by `mockAthleteAiEndpoints` reads this same
  // array on every request, so pushing to it is enough to change what the
  // NEXT poll/refetch returns without a second `page.route()` call.
  const insights = [EXISTING_INSIGHT];

  await mockAthleteShell(page, ATHLETE_C);
  await mockAthleteAiEndpoints(page, ATHLETE_C.id, {
    insights,
    races,
    evolutionSeries: [
      { valida_num: 1, event_id: EVENT_1, event_date: `${SEASON}-02-01`, value: 4, label: "Válida I" },
    ],
  });

  const RUN_ID = "run-e2e-t071";
  const STEP_ID = "step-1";
  const DRAFT_MARKDOWN =
    "## Qué pasó\nSubió dos puestos respecto a la válida anterior.\n## Qué sigue\nTrabajar salidas en pelotón.";

  let launchRequestBody: unknown = null;
  await page.route(
    (url) =>
      isBackend(url) && url.pathname === `/api/athletes/${ATHLETE_C.id}/race-analysis/runs`,
    (route: Route) => {
      launchRequestBody = route.request().postDataJSON();
      route.fulfill({
        status: 200,
        json: {
          run_id: RUN_ID,
          status: "running",
          started_at: new Date().toISOString(),
          status_url: `/api/race-analysis/runs/${RUN_ID}/status`,
          estimated_seconds: 45,
        },
      });
    },
  );

  /** Re-registers `GET /runs/:id/status`. Playwright dispatches to the
   * most-recently-registered matching handler, so each call below acts as
   * an override for every poll from this point forward — see header
   * comment for why this sidesteps modelling the `since` cursor. */
  async function setRunStatusPhase(body: Record<string, unknown>): Promise<void> {
    await page.route(
      (url) =>
        isBackend(url) && url.pathname === `/api/race-analysis/runs/${RUN_ID}/status`,
      jsonRoute(body),
    );
  }

  const nowIso = new Date().toISOString();
  await setRunStatusPhase({
    run_id: RUN_ID,
    state: "running",
    progress_pct: 25,
    current_node: "analyst_agent",
    started_at: nowIso,
    estimated_seconds_remaining: 30,
    new_events: [
      { seq: 1, ts: nowIso, type: "node_start", node: "validate_input", payload: {} },
      { seq: 2, ts: nowIso, type: "node_end", node: "validate_input", payload: {} },
      { seq: 3, ts: nowIso, type: "node_start", node: "analyst_agent", payload: {} },
    ],
    last_seq: 3,
  });

  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/race-analysis/runs/${RUN_ID}/hitl/${STEP_ID}`,
    (route: Route) => {
      // Flip both the run status and the insights list to their
      // post-approval state BEFORE fulfilling, so the refetches the
      // `onSuccess` handlers trigger immediately see the new data.
      insights.push(NEW_INSIGHT);
      void setRunStatusPhase({
        run_id: RUN_ID,
        state: "done",
        progress_pct: 100,
        current_node: null,
        started_at: nowIso,
        estimated_seconds_remaining: 0,
        new_events: [
          { seq: 6, ts: new Date().toISOString(), type: "hitl_response", node: "hitl_gate_review", payload: { step_id: STEP_ID, decision: "approve" } },
          { seq: 7, ts: new Date().toISOString(), type: "node_end", node: "persist_insight", payload: {} },
          { seq: 8, ts: new Date().toISOString(), type: "node_end", node: "notify_coach", payload: {} },
        ],
        last_seq: 8,
      });
      route.fulfill({
        status: 200,
        json: { accepted: true, run_id: RUN_ID, step_id: STEP_ID, next_state: "done" },
      });
    },
  );

  await gotoAthleteAiTab(page, ATHLETE_C.id);

  // --- Launch -----------------------------------------------------------------
  await page.getByTestId("ai-subtab-launch").click();
  await expect(page.getByTestId(`launch-event-${EVENT_2}`)).toBeVisible({ timeout: WAIT_TIMEOUT });
  await page.getByTestId(`launch-event-${EVENT_2}`).click();
  await page.getByTestId("launch-submit").click();

  await expect
    .poll(() => launchRequestBody, { timeout: WAIT_TIMEOUT })
    .toMatchObject({ season: SEASON, event_id: EVENT_2 });

  // `onStarted` switches the sub-tab to "history" automatically.
  await expect(page.getByTestId("ai-subtab-history")).toHaveAttribute("data-state", "active", {
    timeout: WAIT_TIMEOUT,
  });

  // --- Run timeline (running) ---------------------------------------------
  await expect(page.getByTestId("analysis-run-timeline")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByText("En proceso")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("timeline-node-validate_input")).toHaveAttribute(
    "data-status",
    "done",
    { timeout: WAIT_TIMEOUT },
  );

  // --- HITL gate ---------------------------------------------------------------
  await setRunStatusPhase({
    run_id: RUN_ID,
    state: "hitl_waiting",
    progress_pct: 60,
    current_node: "hitl_gate_review",
    started_at: nowIso,
    estimated_seconds_remaining: 10,
    new_events: [
      { seq: 4, ts: new Date().toISOString(), type: "node_end", node: "analyst_agent", payload: {} },
      {
        seq: 5,
        ts: new Date().toISOString(),
        type: "hitl_request",
        node: "hitl_gate_review",
        payload: { step_id: STEP_ID, draft_markdown: DRAFT_MARKDOWN },
      },
    ],
    last_seq: 5,
  });

  await expect(page.getByTestId("hitl-approval-card")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByText("Esperando tu aprobación")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByText(/subió dos puestos/i)).toBeVisible({ timeout: WAIT_TIMEOUT });

  // --- Approve -------------------------------------------------------------
  await page.getByTestId("hitl-approve-button").click();

  // The card and the timeline both go away once the run reaches "done".
  await expect(page.getByTestId("hitl-approval-card")).toHaveCount(0, { timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("analysis-run-timeline")).toHaveCount(0, { timeout: WAIT_TIMEOUT });

  // --- The new insight appears in the history --------------------------------
  await expect(page.getByTestId(`insight-card-${NEW_INSIGHT.id}`)).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
  await expect(page.getByTestId(`insight-card-${EXISTING_INSIGHT.id}`)).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
});

// ---------------------------------------------------------------------------
// T075 — switching athletes with the tab open (US3 regression)
// ---------------------------------------------------------------------------

test("T075: switching athletes with the tab open carries over zero local state", async ({
  page,
}) => {
  const EVENT_A = 71501;
  const INSIGHT_A = makeInsight({
    id: 95001,
    valida_num: 1,
    event_id: EVENT_A,
    event_date: `${SEASON}-03-01`,
    generated_at: `${SEASON}-03-02T10:00:00Z`,
  });

  await mockAthleteShell(page, ATHLETE_A);
  await mockAthleteShell(page, ATHLETE_B);
  await mockAthleteAiEndpoints(page, ATHLETE_A.id, {
    insights: [INSIGHT_A],
    races: [{ event_id: EVENT_A, sequence_number: 1, event_date: `${SEASON}-03-01`, event_name: "Copa Valle I", location: "Cali" }],
    evolutionSeries: [{ valida_num: 1, event_id: EVENT_A, event_date: `${SEASON}-03-01`, value: 2, label: "Válida I" }],
  });
  // Atleta B: temporada limpia, sin análisis — un contraste fuerte contra A
  // que también prueba que la data no se queda pegada del atleta anterior.
  await mockAthleteAiEndpoints(page, ATHLETE_B.id, {
    insights: [],
    races: [],
    evolutionSeries: [],
  });

  await gotoAthleteAiTab(page, ATHLETE_A.id);

  // Warm-up: visit athlete B once, then come back to A, all client-side,
  // BEFORE the real transition under test. Without this, `useAthlete(id)`'s
  // very first fetch for an id never seen before takes `AthleteDetailPage`
  // through its OWN `athleteQuery.isLoading` early-return (a completely
  // different top-level JSX subtree — see the file right after this
  // one's `if (athleteQuery.isLoading) return (...)`), which by itself
  // unmounts and remounts everything under it, `AthleteAIAnalysisTab`
  // included — a remount for the wrong reason that would mask whatever
  // `key={athlete.id}` does or doesn't do. Same problem, same fix as the
  // T010 unit test in `AthleteDetailPage.test.tsx` (which pre-seeds the
  // QueryClient directly); here, with no handle on the QueryClient from
  // Playwright, the equivalent is just visiting both profiles for real
  // first so TanStack Query's cache (`staleTime` 5 min, `gcTime` 24 h —
  // `App.tsx`) is already warm for both by the time the real switch
  // happens a few lines down.
  await spaNavigate(page, `/athletes/${ATHLETE_B.id}?tab=ai_analysis`);
  await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByText("Sin análisis aprobados aún.")).toBeVisible({ timeout: WAIT_TIMEOUT });

  await spaNavigate(page, `/athletes/${ATHLETE_A.id}?tab=ai_analysis`);
  await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByTestId("ai-header-summary")).toBeVisible({ timeout: WAIT_TIMEOUT });

  // Deja el tab en un estado NO default con selección de boletín activa:
  // sub-tab "Histórico" + un insight marcado para el boletín.
  await page.getByTestId("ai-subtab-history").click();
  await expect(page.getByTestId(`insight-card-${INSIGHT_A.id}`)).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
  await page.getByTestId(`insight-checkbox-${INSIGHT_A.id}`).check();
  await expect(page.getByTestId("newsletter-action-bar")).toBeVisible({ timeout: WAIT_TIMEOUT });
  await expect(page.getByText("1 insight seleccionado")).toBeVisible({ timeout: WAIT_TIMEOUT });

  // --- La transición real bajo prueba: A -> B, con la cache de B ya
  // tibia, así que `athleteQuery.isLoading` nunca vuelve a ser true y la
  // única variable que decide si `AthleteAIAnalysisTab` remonta es
  // `key={athlete.id}`. -----------------------------------------------------
  await spaNavigate(page, `/athletes/${ATHLETE_B.id}?tab=ai_analysis`);

  await expect(page).toHaveURL(new RegExp(`/athletes/${ATHLETE_B.id}\\?tab=ai_analysis`), {
    timeout: WAIT_TIMEOUT,
  });
  await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
  // Atleta B no tiene insights (a propósito): confirma que la data mostrada
  // es la SUYA, no la del atleta A arrastrada de algún cache mal keyeado.
  await expect(page.getByText("Sin análisis aprobados aún.")).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });

  // --- Las dos aserciones centrales de la regresión US3 -----------------------
  // 1) El sub-tab vuelve a Panorama (el default de un `useState` fresco) en
  //    vez de seguir en "Histórico" (heredado del atleta A).
  await expect(page.getByTestId("panorama-view")).toBeVisible({ timeout: WAIT_TIMEOUT });
  // 2) La barra de boletín — cuya sola presencia implica
  //    `newsletterSelection.size > 0` — no sobrevive el cambio de atleta.
  //    Sin el fix, seguiría mostrando el insight del atleta A seleccionado,
  //    listo para adjuntarse al boletín del atleta EQUIVOCADO.
  await expect(page.getByTestId("newsletter-action-bar")).toHaveCount(0, {
    timeout: WAIT_TIMEOUT,
  });
});
