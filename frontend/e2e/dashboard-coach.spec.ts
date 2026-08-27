/**
 * E2E — coach home mission control: link-through flows (feature
 * 031-coach-home-mission-control, T058).
 *
 * `contracts/home-tiles.md` fixes a link target for every hero tile and
 * every pending-inbox row on the redesigned `/dashboard` ("Inicio"). This
 * spec drives each one end to end at the real-rendering-engine level (auth +
 * every backend response mocked, same as `coach-navigation.spec.ts` /
 * `target-size.spec.ts`): land on the dashboard, locate the tile/row,
 * click it, and assert both the resulting URL and that the destination
 * page's own real content actually rendered (not just a route match) —
 *
 *   Row 1, Tile 1 — "Próxima sesión"              -> /training/sessions/{id}
 *   Row 1, Tile 2 — "Próxima carrera Copa Valle"   -> /competitions/{id}
 *   Row 2 — Resultados por importar                -> /competitions?filter=needs-results
 *   Row 2 — Actividades sin enlazar                 -> /activities?linked=false
 *   Row 2 — Boletines pendientes del mes            -> /training/athlete-newsletters
 *   Row 2 — Consentimientos pendientes              -> /athletes
 *   Row 2 — Insights IA desactualizados             -> /competitions/insights/season/{year}
 *
 * Auth + backend mocking mirror `coach-navigation.spec.ts` / `target-size.
 * spec.ts`: the persisted Zustand `auth-session` shape is written directly
 * into `sessionStorage` via `addInitScript` (skips the real login round
 * trip), and every backend route is matched by URL predicate — never a
 * glob string — so Vite's own dev-server module requests (port 5173) are
 * never swallowed (`src/api/*.ts` can share path segments with a real
 * `/api/*` backend route).
 *
 * All fixture dates use a far-future event/session date (2099) rather than
 * a date relative to "today" — the tiles' own "is this upcoming/ended"
 * logic runs against the browser's real clock (no `page.clock` override
 * here), so a fixed relative-to-"now" fixture would silently rot as the
 * suite ages. A fixed 2020 date is used for the one row that requires a
 * *past* event ("Resultados por importar"), for the same reason.
 *
 * Run just this file: `cd frontend && npx playwright test e2e/dashboard-coach.spec.ts`
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const WAIT_TIMEOUT = 15_000;

const SESSION_ID = 601;
const PAST_RACE_EVENT_ID = 9001;
const FUTURE_RACE_EVENT_ID = 9002;

/**
 * `currentSeason()` (`src/lib/datetime.ts`) is just "the current year in
 * America/Bogota" — matches the real calendar year this suite runs in
 * (2026), same convention `target-size.spec.ts` / `CompetitionsListPage`
 * already hardcode for their own 2026 fixtures.
 */
const CURRENT_SEASON = 2026;

// ---------------------------------------------------------------------------
// Auth — mirrors coach-navigation.spec.ts / target-size.spec.ts: write the
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
  access_token: "e2e-dashboard-coach-access",
  refresh_token: "e2e-dashboard-coach-refresh",
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

// ---- Fixtures ---------------------------------------------------------------

const NEXT_SESSION = {
  id: SESSION_ID,
  club_id: 1,
  created_by_user_id: 1,
  status: "planned",
  scheduled_date: "2099-06-01",
  scheduled_start_time: "16:00:00",
  duration_min: 90,
  location: "Cancha Ginebra",
  technical_focus: "Técnica de curvas y frenada",
  description: "Circuito técnico con énfasis en control de velocidad.",
  route_text: null,
  strava_url: null,
  route_file_path: null,
  coach_notes: null,
  created_at: "2026-06-01T00:00:00Z",
  updated_at: "2026-06-01T00:00:00Z",
};

/** Past event, missing results — feeds the "Resultados por importar" row. */
const PAST_RACE_EVENT = {
  id: PAST_RACE_EVENT_ID,
  series_id: 1,
  sequence_number: 1,
  name: "Copa Valle I — Sevilla",
  event_date: "2020-01-15",
  location: "Sevilla",
  is_championship: false,
  status: "completed" as const,
  has_results: false,
  has_calendar_event: true,
  conditions_completeness: "complete" as const,
};

/** Future event — feeds the "Próxima carrera Copa Valle" hero tile. */
const FUTURE_RACE_EVENT = {
  id: FUTURE_RACE_EVENT_ID,
  series_id: 1,
  sequence_number: 5,
  name: "Copa Valle V — Palmira",
  event_date: "2099-08-01",
  location: "Palmira",
  is_championship: false,
  status: "scheduled" as const,
  has_results: false,
  has_calendar_event: true,
  conditions_completeness: "complete" as const,
};

const RACE_EVENTS_LIST = {
  items: [PAST_RACE_EVENT, FUTURE_RACE_EVENT],
  total: 2,
};

/** Full `RaceEventRead` shape for the detail endpoint hit by CompetitionDetailPage. */
const FUTURE_RACE_EVENT_DETAIL = {
  ...FUTURE_RACE_EVENT,
  climate: null,
  temperature_c: null,
  surface_condition: null,
  altitude_msnm: null,
  weather_notes: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
  created_by_user_id: 1,
};

const ACTIVITIES_LIST = { items: [] as unknown[], total: 3, page: 1, page_size: 1 };

const NEWSLETTER_SUMMARY = {
  items: [
    {
      athlete_id: 11,
      newsletter_id: 501,
      status: "draft",
      generated_at: "2026-07-01T00:00:00Z",
      sent_at: null,
    },
    {
      athlete_id: 12,
      newsletter_id: 502,
      status: "sent",
      generated_at: "2026-07-01T00:00:00Z",
      sent_at: "2026-07-02T00:00:00Z",
    },
  ],
};

const COACH_SUMMARY = {
  generated_at: "2026-07-01T00:00:00Z",
  consents_pending: 2,
  insights_stale: 4,
  // Tile omitted entirely when null (contracts/home-tiles.md) — the meter
  // isn't part of this task's link-through flows.
  weekly_load: null,
};

const ALERTS_SUMMARY = {
  overdue: 0,
  due_soon: 0,
  ok: 0,
  never_measured: 0,
  rapid_growth_count: 0,
  athletes: [] as unknown[],
};

const SEASON_PANORAMA = {
  season: CURRENT_SEASON,
  total_athletes: 0,
  items: [] as unknown[],
};

// ---- Route registration -------------------------------------------------

/**
 * Everything `/dashboard` needs for both hero tiles + all five pending-inbox
 * rows to resolve to a real, clickable state.
 */
async function mockDashboardLanding(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/athletes/alerts",
    jsonRoute(ALERTS_SUMMARY),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/training-sessions",
    jsonRoute([NEXT_SESSION]),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/race-analysis/race-events/",
    jsonRoute(RACE_EVENTS_LIST),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/activities",
    jsonRoute(ACTIVITIES_LIST),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/training/athlete-newsletters/summary",
    jsonRoute(NEWSLETTER_SUMMARY),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/dashboard/coach-summary",
    jsonRoute(COACH_SUMMARY),
  );
}

/** `/api/athletes` (list) empty — shared by every destination page that
 * renders an athlete picker/roster as a side concern (ActivityReviewPage,
 * AthleteNewslettersDashboardPage, AthletesListPage). */
async function mockAthletesEmpty(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/athletes",
    jsonRoute({ items: [] }),
  );
}

/** `/training/sessions/{id}` — mirrors target-size.spec.ts's session-detail mock. */
async function mockSessionDetailApi(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/training-sessions/${SESSION_ID}`,
    jsonRoute(NEXT_SESSION),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/training-sessions/${SESSION_ID}/attendance`,
    jsonRoute([]),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/training-sessions/${SESSION_ID}/media`,
    jsonRoute([]),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/training-sessions/${SESSION_ID}/activities`,
    jsonRoute({ items: [] }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/strength/sessions/${SESSION_ID}/blocks`,
    jsonRoute({ items: [] }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/intervals/sessions/${SESSION_ID}/structure`,
    jsonRoute({ detail: "not found" }, 404),
  );
}

/** `/competitions/{id}` — default "info" tab only needs the event itself
 * (InfoTab is presentational; the series-level lookup only fires for
 * championships, and this fixture is a regular válida). */
async function mockCompetitionDetailApi(page: Page): Promise<void> {
  await page.route(
    (url) =>
      isBackend(url) && url.pathname === `/api/race-analysis/race-events/${FUTURE_RACE_EVENT_ID}`,
    jsonRoute(FUTURE_RACE_EVENT_DETAIL),
  );
}

/** `/competitions/insights/season/{year}` (SeasonInsightsPage). */
async function mockSeasonInsightsApi(page: Page): Promise<void> {
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/race-analysis/insights/season/${CURRENT_SEASON}`,
    jsonRoute(SEASON_PANORAMA),
  );
}

async function gotoDashboard(page: Page): Promise<void> {
  await page.goto("/dashboard");
  // Ver la nota en `coach-navigation.spec.ts`: el saludo de la feature 035
  // reemplazó al <h1> "Dashboard", así que la puerta es el `data-testid`.
  await expect(page.getByTestId("dashboard-heading")).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Feature 031 (T058) — coach home: link-through flows", () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockHealth(page);
    await mockDashboardLanding(page);
  });

  test("Row 1, Tile 1 'Próxima sesión' links to /training/sessions/{id}", async ({ page }) => {
    await mockSessionDetailApi(page);
    await gotoDashboard(page);

    const tile = page.getByRole("link", { name: /Próxima sesión/ });
    await expect(tile).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(tile).toContainText("Técnica de curvas y frenada");

    await tile.click();
    await page.waitForURL(`**/training/sessions/${SESSION_ID}`, { timeout: WAIT_TIMEOUT });

    expect(new URL(page.url()).pathname).toBe(`/training/sessions/${SESSION_ID}`);
    await expect(page.getByTestId("session-detail-header")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
  });

  test("Row 1, Tile 2 'Próxima carrera Copa Valle' links to /competitions/{id}", async ({
    page,
  }) => {
    await mockCompetitionDetailApi(page);
    await gotoDashboard(page);

    const tile = page.getByRole("link", { name: /Próxima carrera Copa Valle/ });
    await expect(tile).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(tile).toContainText(FUTURE_RACE_EVENT.name);

    await tile.click();
    await page.waitForURL(`**/competitions/${FUTURE_RACE_EVENT_ID}`, { timeout: WAIT_TIMEOUT });

    expect(new URL(page.url()).pathname).toBe(`/competitions/${FUTURE_RACE_EVENT_ID}`);
    await expect(
      page.getByRole("heading", { name: FUTURE_RACE_EVENT.name }),
    ).toBeVisible({ timeout: WAIT_TIMEOUT });
  });

  test("Row 2 'Resultados por importar' links to /competitions?filter=needs-results", async ({
    page,
  }) => {
    await gotoDashboard(page);

    const row = page.getByRole("link", { name: /Resultados por importar/ });
    await expect(row).toBeVisible({ timeout: WAIT_TIMEOUT });

    await row.click();
    await page.waitForURL("**/competitions?filter=needs-results", { timeout: WAIT_TIMEOUT });

    const landed = new URL(page.url());
    expect(landed.pathname).toBe("/competitions");
    expect(landed.searchParams.get("filter")).toBe("needs-results");
    await expect(page.getByRole("heading", { name: "Competencias" })).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
  });

  test("Row 2 'Actividades sin enlazar' links to /activities?linked=false", async ({ page }) => {
    await mockAthletesEmpty(page);
    await gotoDashboard(page);

    const row = page.getByRole("link", { name: /Actividades sin enlazar/ });
    await expect(row).toBeVisible({ timeout: WAIT_TIMEOUT });

    await row.click();
    await page.waitForURL("**/activities?linked=false", { timeout: WAIT_TIMEOUT });

    const landed = new URL(page.url());
    expect(landed.pathname).toBe("/activities");
    expect(landed.searchParams.get("linked")).toBe("false");
    await expect(page.getByRole("heading", { name: "Revisión de actividades" })).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
  });

  test("Row 2 'Boletines pendientes del mes' links to /training/athlete-newsletters", async ({
    page,
  }) => {
    await mockAthletesEmpty(page);
    await gotoDashboard(page);

    const row = page.getByRole("link", { name: /Boletines pendientes del mes/ });
    await expect(row).toBeVisible({ timeout: WAIT_TIMEOUT });

    await row.click();
    await page.waitForURL("**/training/athlete-newsletters", { timeout: WAIT_TIMEOUT });

    expect(new URL(page.url()).pathname).toBe("/training/athlete-newsletters");
    await expect(page.getByRole("heading", { name: "Boletines" })).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
  });

  test("Row 2 'Consentimientos pendientes' links to /athletes", async ({ page }) => {
    await mockAthletesEmpty(page);
    await gotoDashboard(page);

    const row = page.getByRole("link", { name: /Consentimientos pendientes/ });
    await expect(row).toBeVisible({ timeout: WAIT_TIMEOUT });

    await row.click();
    await page.waitForURL("**/athletes", { timeout: WAIT_TIMEOUT });

    expect(new URL(page.url()).pathname).toBe("/athletes");
    await expect(page.getByRole("heading", { name: "Atletas" })).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
  });

  test("Row 2 'Insights IA desactualizados' links to /competitions/insights/season/{year}", async ({
    page,
  }) => {
    await mockSeasonInsightsApi(page);
    await gotoDashboard(page);

    const row = page.getByRole("link", { name: /Insights IA desactualizados/ });
    await expect(row).toBeVisible({ timeout: WAIT_TIMEOUT });

    await row.click();
    await page.waitForURL(`**/competitions/insights/season/${CURRENT_SEASON}`, {
      timeout: WAIT_TIMEOUT,
    });

    expect(new URL(page.url()).pathname).toBe(
      `/competitions/insights/season/${CURRENT_SEASON}`,
    );
    await expect(
      page.getByRole("heading", { name: `Panorama de temporada ${CURRENT_SEASON}` }),
    ).toBeVisible({ timeout: WAIT_TIMEOUT });
  });
});
