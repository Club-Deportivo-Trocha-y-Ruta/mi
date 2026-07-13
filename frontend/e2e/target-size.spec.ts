/**
 * E2E — target-size sweep (feature 028-frontend-design-foundation, US1, T023).
 *
 * WCAG 2.5.8 Target Size (Minimum, AA) sets a 24×24 CSS px floor; this
 * project's constitution (Principle III / CLAUDE.md "Touch targets MUST be
 * >=48x48px") is stricter — every interactive control must be >=48×48 CSS px
 * so a gloved finger can operate it on a tablet in direct sunlight. jest-axe
 * in jsdom cannot measure rendered size (no layout engine — research.md R7),
 * so this has to run on a real rendering engine.
 *
 * Sweeps four representative coach screens and asserts the *real*,
 * on-screen `boundingBox()` for every `a`, `button`, `[role=button]`, and
 * form input (`input`, `select`, `textarea`) that is actually rendered and
 * visible:
 *
 *   1. Session detail (`/training/sessions/:id`) — incl. the ToggleGroup-
 *      based effort rubric (T018) inside the Asistencia section.
 *   2. Competitions results table (`/competitions/:id?tab=results`) — incl.
 *      the per-row "note" button and "Analizar con IA" button (T021).
 *   3. Coach dashboard (`/dashboard`) — incl. the feature-031 mission-control
 *      rewrite: `NextSessionTile`, `NextRaceTile`, `WeeklyLoadMeter`, and
 *      `PendingInbox`'s five rows (T057).
 *   4. Sessions list (`/training/sessions`) — representative list page.
 *
 * Self-contained, no backend/docker required (there is no live backend in
 * this environment either way): auth + every API response are mocked via
 * `page.route`, mirroring `calendar-coach.spec.ts`'s `addInitScript`-into-
 * `sessionStorage` pattern (writes the persisted Zustand `auth-session`
 * shape directly, skipping the real POST /api/auth/login) plus
 * `cold-start.spec.ts`'s URL-predicate routing (`url.port !== "5173"`) so
 * mocks never intercept Vite's own dev-server module requests — a glob like
 * `**\/api/training-sessions/**` would also match the *source* file
 * `/src/api/trainingSessions.ts` that Vite serves on port 5173.
 *
 * Run just this file: `cd frontend && npx playwright test e2e/target-size.spec.ts`
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Constitution III / CLAUDE.md: every touch target must be >=48x48 CSS px. */
const MIN_TARGET_SIZE = 48;

/** Generous but bounded — every response here is mocked, nothing waits on a real network. */
const WAIT_TIMEOUT = 15_000;

const SESSION_ID = 501;
const RACE_EVENT_ID = 701;
const OUR_ATHLETE_ID = 11;

// ---------------------------------------------------------------------------
// Auth — mirrors calendar-coach.spec.ts: write the persisted Zustand
// `auth-session` shape directly into sessionStorage so no real login
// round-trip is needed.
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
  access_token: "e2e-target-size-access",
  refresh_token: "e2e-target-size-refresh",
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
// Backend mocking
// ---------------------------------------------------------------------------

/**
 * Every predicate below is checked against the request URL, never a glob
 * string — see cold-start.spec.ts's header comment for why: Vite dev-server
 * module requests (port 5173) can contain the same literal path segments as
 * a backend API route (e.g. `/src/api/trainingSessions.ts` vs.
 * `/api/training-sessions`), so a glob match risks swallowing app source
 * files and blanking the page.
 */
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

// ---- Fixtures --------------------------------------------------------------

const SESSION = {
  id: SESSION_ID,
  club_id: 1,
  created_by_user_id: 1,
  status: "planned",
  scheduled_date: "2026-07-20",
  scheduled_start_time: "15:30:00",
  duration_min: 90,
  location: "Pista XCO Buitrera",
  technical_focus: "Técnica de frenada y curvas",
  description: "Circuito técnico con énfasis en frenada progresiva.",
  route_text: null,
  strava_url: null,
  route_file_path: null,
  coach_notes: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

// `status: "presente"` is what makes `AttendanceTable` render the effort
// rubric (T018) — `ALLOWS_RUBRIC` in useAttendanceForm.ts gates it on
// "presente" | "tarde".
const ATTENDANCE = [
  {
    id: 1,
    session_id: SESSION_ID,
    athlete_id: OUR_ATHLETE_ID,
    athlete_name: "Sebastián García",
    status: "presente",
    excuse_reason: null,
    rpe_omni: 5,
    rubric_effort: 3,
    rubric_attitude: 3,
    rubric_technique: 3,
    individual_feedback: null,
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
  },
];

const SESSIONS_LIST = [
  { ...SESSION, id: 501, status: "planned" },
  {
    ...SESSION,
    id: 502,
    status: "executed",
    scheduled_date: "2026-07-10",
    technical_focus: "Salida larga de resistencia",
    attendance_summary: {
      total: 5,
      presentes: 4,
      ausentes: 1,
      justificados: 0,
      tardes: 0,
      lesionados: 0,
    },
  },
];

const ALERTS_SUMMARY = {
  overdue: 1,
  due_soon: 1,
  ok: 3,
  never_measured: 0,
  rapid_growth_count: 0,
  athletes: [
    {
      athlete_id: 21,
      athlete_name: "Valentina Ríos",
      sex: "F",
      age_decimal: 12.4,
      category: "Infantil",
      measurement_status: "overdue",
      last_measurement_date: "2026-01-10",
      next_due_date: "2026-04-10",
      days_overdue: 90,
      current_phv_status: "Pre-PHV",
      measurement_interval_days: 90,
      growth_velocity_cm_month: null,
      growth_alerts: [],
      training_implications: null,
    },
    {
      athlete_id: 22,
      athlete_name: "Mateo Rojas",
      sex: "M",
      age_decimal: 13.1,
      category: "Juvenil",
      measurement_status: "due_soon",
      last_measurement_date: "2026-05-01",
      next_due_date: "2026-08-01",
      days_overdue: -10,
      current_phv_status: "Circa-PHV",
      measurement_interval_days: 90,
      growth_velocity_cm_month: null,
      growth_alerts: [],
      training_implications: null,
    },
  ],
};

const RACE_EVENT = {
  id: RACE_EVENT_ID,
  series_id: 1,
  sequence_number: 4,
  name: "Copa Valle IV — Cali",
  event_date: "2026-05-17",
  location: "Cali",
  is_championship: false,
  status: "completed",
  climate: null,
  temperature_c: null,
  surface_condition: null,
  altitude_msnm: null,
  weather_notes: null,
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-17T00:00:00Z",
  created_by_user_id: 1,
  has_calendar_event: true,
};

// One linked "our club" row (exercises the T021 note button + "Analizar con
// IA" button) and one rival row (exercises the ordinary, non-actionable path).
const RACE_RESULTS = {
  race_event_id: RACE_EVENT_ID,
  event_name: RACE_EVENT.name,
  event_date: RACE_EVENT.event_date,
  location: RACE_EVENT.location,
  status: "completed",
  categories: [
    {
      category_id: 1,
      code: "INF_M",
      label: "Infantil Masculino",
      rows: [
        {
          result_id: 9001,
          position: 1,
          competitor_id: 5001,
          display_name: "Sebastián García",
          club_text: "Trocha y Ruta",
          athlete_id: OUR_ATHLETE_ID,
          is_our_club: true,
          status: "finished",
          race_time_ms: 3_540_000,
          laps_behind: null,
          points_awarded: 100,
          bib_number: 12,
          coach_note: null,
          coach_note_updated_at: null,
        },
        {
          result_id: 9002,
          position: 2,
          competitor_id: 5002,
          display_name: "Rival Uno",
          club_text: "Otro Club",
          athlete_id: null,
          is_our_club: false,
          status: "finished",
          race_time_ms: 3_600_000,
          laps_behind: null,
          points_awarded: 90,
          bib_number: 7,
          coach_note: null,
          coach_note_updated_at: null,
        },
      ],
    },
  ],
};

const CLUB_INSIGHTS_BY_RACE = {
  race_event_id: RACE_EVENT_ID,
  race_event_label: RACE_EVENT.name,
  total_athletes: 1,
  items: [] as unknown[],
};

// ---- Dashboard (031) fixtures — NextSessionTile / NextRaceTile /
// WeeklyLoadMeter / PendingInbox ---------------------------------------------

// One upcoming race (`event_date >= today`) so NextRaceTile has a hero to
// render, plus one past race missing results so PendingInbox's "Resultados
// por importar" row resolves to a non-zero, clickable row instead of being
// skeleton/empty.
const DASHBOARD_RACE_EVENTS = {
  items: [
    {
      id: 705,
      series_id: 5,
      sequence_number: 5,
      name: "Copa Valle V — Palmira",
      event_date: "2026-08-01",
      location: "Palmira",
      is_championship: false,
      status: "scheduled",
      has_results: false,
      has_calendar_event: true,
      conditions_completeness: "empty",
    },
    {
      id: 706,
      series_id: 4,
      sequence_number: 1,
      name: "Copa Valle CD — Ginebra",
      event_date: "2026-06-12",
      location: "Ginebra",
      is_championship: true,
      status: "completed",
      has_results: false,
      has_calendar_event: true,
      conditions_completeness: "complete",
    },
  ],
  total: 2,
};

// `total: 3` so PendingInbox's "Actividades sin enlazar" row renders as a
// real, non-zero clickable row (items themselves are irrelevant — the row
// only reads `.total`, per `useActivityReview({ page_size: 1 })`).
const DASHBOARD_ACTIVITIES_UNLINKED = {
  items: [] as unknown[],
  total: 3,
  page: 1,
  page_size: 1,
};

const DASHBOARD_NEWSLETTER_SUMMARY = {
  year: 2026,
  month: 7,
  items: [
    {
      athlete_id: OUR_ATHLETE_ID,
      newsletter_id: 1,
      status: "draft",
      generated_at: "2026-07-01T00:00:00Z",
      sent_at: null,
    },
  ],
};

const DASHBOARD_COACH_SUMMARY = {
  generated_at: "2026-07-12T12:00:00Z",
  consents_pending: 2,
  insights_stale: 1,
  weekly_load: [
    { age_band: "10-12", planned_minutes: 300, cap_minutes: 600, athlete_count: 5 },
    { age_band: "13-15", planned_minutes: 700, cap_minutes: 780, athlete_count: 6 },
  ],
};

// ---- Per-page route registration -------------------------------------------

async function mockSessionDetailApi(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/training-sessions/${SESSION_ID}`,
    jsonRoute(SESSION),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/training-sessions/${SESSION_ID}/attendance`,
    jsonRoute(ATTENDANCE),
  );
  // Defensive: the autosave debounce in useAttendanceForm.ts should never
  // fire on initial mount (values unchanged), but mock the PATCH anyway so
  // nothing ever falls through to a real network attempt.
  await page.route(
    (url) =>
      isBackend(url) &&
      new RegExp(`^/api/training-sessions/${SESSION_ID}/attendance/\\d+$`).test(url.pathname),
    jsonRoute(ATTENDANCE[0]),
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
    (url) => isBackend(url) && url.pathname === "/api/activities",
    jsonRoute({ items: [], total: 0, page: 1, page_size: 30 }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/strength/sessions/${SESSION_ID}/blocks`,
    jsonRoute({ items: [] }),
  );
  // No interval structure yet — natural "empty" state (useSessionStructure
  // has retry:false and treats 404 as "nothing attached").
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/intervals/sessions/${SESSION_ID}/structure`,
    jsonRoute({ detail: "not found" }, 404),
  );
}

async function mockSessionsListApi(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/training-sessions",
    jsonRoute(SESSIONS_LIST),
  );
}

async function mockDashboardApi(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/athletes/alerts",
    jsonRoute(ALERTS_SUMMARY),
  );
  // NextSessionTile (feature 031) — same list endpoint as sessions list,
  // reused as-is: `SESSION_LIST`'s id 501 is `status: "planned"` with a
  // `scheduled_date` inside the next 14 days, so it resolves to a real tile.
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/training-sessions",
    jsonRoute(SESSIONS_LIST),
  );
  // NextRaceTile + PendingInbox's "Resultados por importar" row — same
  // queryKey/endpoint, mocked once (research.md R2: no duplicate request).
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/race-analysis/race-events/",
    jsonRoute(DASHBOARD_RACE_EVENTS),
  );
  // PendingInbox's "Actividades sin enlazar" row.
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/activities",
    jsonRoute(DASHBOARD_ACTIVITIES_UNLINKED),
  );
  // PendingInbox's "Boletines pendientes del mes" row.
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/training/athlete-newsletters/summary",
    jsonRoute(DASHBOARD_NEWSLETTER_SUMMARY),
  );
  // WeeklyLoadMeter + PendingInbox's "Consentimientos pendientes" /
  // "Insights IA desactualizados" rows.
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/dashboard/coach-summary",
    jsonRoute(DASHBOARD_COACH_SUMMARY),
  );
}

async function mockCompetitionResultsApi(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/race-analysis/race-events/${RACE_EVENT_ID}`,
    jsonRoute(RACE_EVENT),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/race-analysis/race-events/${RACE_EVENT_ID}/results`,
    jsonRoute(RACE_RESULTS),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/races/${RACE_EVENT_ID}/club-insights`,
    jsonRoute(CLUB_INSIGHTS_BY_RACE),
  );
}

// ---------------------------------------------------------------------------
// Target-size sweep
// ---------------------------------------------------------------------------

const INTERACTIVE_SELECTOR = "a, button, [role='button'], input, select, textarea";

/**
 * Elements intentionally exempt from the ≥48×48px sweep, each documented
 * with which rule earns it the exemption:
 *
 *  - WCAG 2.5.8's *inline* exception: a target "in a sentence or block of
 *    text" whose size is governed by the surrounding text's line-height,
 *    not by the author (e.g. a plain-prose link/trigger word embedded
 *    mid-sentence).
 *  - Not currently a rendered target at all: a control that is
 *    intentionally off-screen/clipped in its resting state and only
 *    becomes a normal, full-size target once it receives keyboard focus
 *    (the standard "skip link" pattern) — Playwright's `isVisible()`
 *    doesn't know about this convention and would otherwise flag its 1×1px
 *    resting `boundingBox()`.
 *
 * Selectors are plain Playwright locator strings (not passed through
 * native `Element.matches()`), so Playwright-only syntax like `:text-is()`
 * is fine here.
 */
const ALLOWLIST_SELECTORS: readonly string[] = [
  // Inline exception — SessionDetailPage's route-upload dropzone: "Arrastra
  // un archivo .gpx o .fit aquí, o **selecciónalo**" — the trigger is a
  // clickable word inside a sentence, not an independently-sized control.
  'button:text-is("selecciónalo")',
  // Not a rendered target while resting — AppShell's "Saltar a contenido"
  // skip link (Tailwind `sr-only`, `focus:not-sr-only`): 1×1px until it
  // receives focus, then expands to a full padded target.
  'a[href="#main-content"]',
];

interface Violation {
  tag: string;
  name: string;
  width: number;
  height: number;
}

/** Tags every element matched by an allowlist entry with a throwaway marker
 * attribute. Membership can't be checked with native `Element.matches()`
 * later (Playwright-only selector syntax isn't valid CSS), so this resolves
 * each allowlist locator once, up front, and stamps the real DOM nodes. */
async function markAllowlisted(page: Page, selectors: readonly string[]): Promise<void> {
  for (const selector of selectors) {
    const locator = page.locator(selector);
    const count = await locator.count();
    for (let i = 0; i < count; i += 1) {
      await locator.nth(i).evaluate((el) => el.setAttribute("data-tsize-allowlisted", "1"));
    }
  }
}

/**
 * Sweeps every rendered `a` / `button` / `[role=button]` / form-input
 * element on the current page and returns those whose real, on-screen
 * `boundingBox()` is smaller than `MIN_TARGET_SIZE` in either dimension.
 * Elements matched by `ALLOWLIST_SELECTORS` and elements that aren't
 * currently visible (`display:none`, e.g. the mobile-only nav hamburger at
 * this desktop viewport) are skipped.
 */
async function findTargetSizeViolations(page: Page): Promise<Violation[]> {
  await markAllowlisted(page, ALLOWLIST_SELECTORS);

  const locator = page.locator(INTERACTIVE_SELECTOR);
  const count = await locator.count();
  const violations: Violation[] = [];

  for (let i = 0; i < count; i += 1) {
    const el = locator.nth(i);

    const isAllowlisted = await el.evaluate((node) => node.hasAttribute("data-tsize-allowlisted"));
    if (isAllowlisted) continue;
    if (!(await el.isVisible())) continue;

    const box = await el.boundingBox();
    if (!box) continue;
    if (box.width < MIN_TARGET_SIZE || box.height < MIN_TARGET_SIZE) {
      const info = await el.evaluate((node) => {
        const element = node as HTMLElement;
        const id = element.id;
        const label = id
          ? document.querySelector(`label[for="${CSS.escape(id)}"]`)?.textContent?.trim()
          : null;
        const text = element.innerText?.trim();
        return {
          tag: element.tagName.toLowerCase(),
          name:
            element.getAttribute("aria-label") ||
            label ||
            element.getAttribute("data-testid") ||
            (text ? text.slice(0, 40) : "") ||
            element.getAttribute("placeholder") ||
            element.getAttribute("name") ||
            element.getAttribute("type") ||
            "",
        };
      });
      violations.push({
        tag: info.tag,
        name: info.name || "(sin nombre accesible)",
        width: Math.round(box.width),
        height: Math.round(box.height),
      });
    }
  }

  return violations;
}

function describeViolations(violations: Violation[]): string {
  return violations
    .map(
      (v) =>
        `  - <${v.tag}> "${v.name}" → ${v.width}×${v.height}px (need ≥${MIN_TARGET_SIZE}×${MIN_TARGET_SIZE})`,
    )
    .join("\n");
}

async function expectNoTargetSizeViolations(page: Page, pageLabel: string): Promise<void> {
  const violations = await findTargetSizeViolations(page);
  if (violations.length > 0) {
    // Visible in --reporter=list/line output even if the assertion message
    // below gets truncated.
    // eslint-disable-next-line no-console
    console.log(`[target-size] ${pageLabel}:\n${describeViolations(violations)}`);
  }
  expect(
    violations,
    `${pageLabel}: ${violations.length} target-size violation(s) found:\n${describeViolations(violations)}`,
  ).toEqual([]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Feature 028 (T023) — target-size sweep (>=48x48px)", () => {
  test.beforeEach(async ({ page }) => {
    await setupAuth(page);
    await mockHealth(page);
  });

  test("session detail — every control >=48x48px, incl. the effort rubric (T018)", async ({
    page,
  }) => {
    await mockSessionDetailApi(page);

    await page.goto(`/training/sessions/${SESSION_ID}`);
    await expect(page.getByTestId("session-detail-header")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });

    // Confirm the T018 rewrite actually rendered: a discrete ToggleGroup
    // option with this exact accessible name only exists post-rewrite (the
    // pre-rewrite <input type="range"> exposed no such control at all).
    // Radix's single-select ToggleGroup renders each option as a real
    // <button> element (caught by the sweep's plain `button` tag selector
    // below regardless of ARIA role) exposed with role="radio" (mutually
    // exclusive semantics) — so the accessible-name lookup here must use
    // that role, not "button".
    await expect(
      page.getByRole("radio", { name: "RPE OMNI 0-10: 5 — Moderado" }),
    ).toBeVisible({ timeout: WAIT_TIMEOUT });

    await expectNoTargetSizeViolations(page, "Session detail");
  });

  test("competitions results table — every control >=48x48px, incl. note + AI buttons (T021)", async ({
    page,
  }) => {
    await mockCompetitionResultsApi(page);

    await page.goto(`/competitions/${RACE_EVENT_ID}?tab=results`);
    await expect(page.getByTestId("competition-title")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });

    // Confirm T021's two fixes actually rendered before sweeping.
    await expect(page.getByTestId("note-btn-5001")).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(page.getByTestId(`ai-launch-btn-${OUR_ATHLETE_ID}`)).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });

    await expectNoTargetSizeViolations(page, "Competitions results table");
  });

  test("coach dashboard — every control >=48x48px, incl. next-session/next-race tiles, weekly-load meter, and pending inbox (T057)", async ({
    page,
  }) => {
    await mockDashboardApi(page);

    await page.goto("/dashboard");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
    await expect(page.getByText("Mediciones pendientes")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });

    // Confirm the feature-031 mission-control tiles/rows actually rendered
    // (not skeletons) before sweeping, so a stalled fetch can't silently
    // shrink the swept surface down to zero interactive elements.
    await expect(page.getByText("Próxima sesión")).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(page.getByText(SESSION.technical_focus)).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
    await expect(page.getByText("Próxima carrera Copa Valle")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
    await expect(page.getByText(DASHBOARD_RACE_EVENTS.items[0].name)).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
    await expect(page.getByText("Carga semanal")).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(page.getByText("Pendientes de esta semana")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
    await expect(page.getByText("Resultados por importar")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });
    await expect(page.getByText("Consentimientos pendientes")).toBeVisible({
      timeout: WAIT_TIMEOUT,
    });

    await expectNoTargetSizeViolations(page, "Coach dashboard");
  });

  test("sessions list — every control >=48x48px (representative list page)", async ({
    page,
  }) => {
    await mockSessionsListApi(page);

    await page.goto("/training/sessions");
    await expect(
      page.getByRole("heading", { name: /sesiones de entrenamiento/i }),
    ).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(page.getByRole("table")).toBeVisible({ timeout: WAIT_TIMEOUT });

    await expectNoTargetSizeViolations(page, "Sessions list");
  });
});
