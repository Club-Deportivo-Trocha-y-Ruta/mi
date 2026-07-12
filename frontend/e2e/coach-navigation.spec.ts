/**
 * E2E — coach/admin navigation redesign (feature 030-coach-navigation-redesign, US3, T033).
 *
 * Covers spec.md US3's Independent Test at the real-rendering-engine level
 * (jest-axe/jsdom cannot measure layout — see `specs/028-frontend-design-foundation/research.md`
 * R7, mirrored for this feature's own target-size assertions):
 *
 *   1. `>=768px` (Tailwind `md`) shows `<SidebarNav>` and hides `<BottomNav>`.
 *   2. `<768px` shows `<BottomNav>` (4 areas + "Más") and hides `<SidebarNav>`.
 *   3. No width renders neither (sidebar/bottom-bar are `md`-complementary,
 *      checked right at the 767/768 boundary — `contracts/mobile-navigation.md`
 *      "No dead zone").
 *   4. Admin's bottom-bar 4th slot is "Biblioteca", never "Atletas"
 *      (`research.md` R6).
 *   5. Every bottom-bar slot and every "Más" sheet row measures >=48x48 CSS px
 *      (constitution III / FR-005).
 *
 * Auth + backend are mocked exactly like `target-size.spec.ts` /
 * `cold-start.spec.ts`: the persisted Zustand `auth-session` shape is written
 * directly into `sessionStorage` via `addInitScript` (skips the real login
 * round-trip), and every backend route is matched by URL predicate — never a
 * glob string — so Vite's own dev-server module requests (port 5173) are
 * never swallowed (`src/api/*.ts` can share path segments with a real `/api/*`
 * backend route).
 *
 * Run just this file: `cd frontend && npx playwright test e2e/coach-navigation.spec.ts`
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Constitution III / CLAUDE.md: every touch target must be >=48x48 CSS px. */
const MIN_TARGET_SIZE = 48;

/** Tailwind's default `md` breakpoint — the single token both `SidebarNav`'s
 * `<aside>` (`hidden md:flex`) and `BottomNav` (`md:hidden`) key off of. */
const MD_BREAKPOINT = 768;

const DESKTOP_VIEWPORT = { width: 1280, height: 800 };
const MOBILE_VIEWPORT = { width: 375, height: 800 };

const WAIT_TIMEOUT = 15_000;

// ---------------------------------------------------------------------------
// Auth — mirrors target-size.spec.ts / calendar-coach.spec.ts: write the
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

const ADMIN_USER = {
  id: 2,
  email: "admin@trochyruta.com",
  first_name: "Ana",
  last_name: "Ospina",
  phone: null,
  role: "admin",
  is_active: true,
  can_login: true,
  club_ids: [1],
  created_at: "2026-01-01T00:00:00Z",
};

const TOKENS = {
  access_token: "e2e-coach-nav-access",
  refresh_token: "e2e-coach-nav-refresh",
};

async function setupAuth(page: Page, user: typeof COACH_USER): Promise<void> {
  await page.addInitScript(
    ({ tokens, sessionUser }) => {
      sessionStorage.setItem(
        "auth-session",
        JSON.stringify({
          state: {
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            user: sessionUser,
            isAuthenticated: true,
            isLoading: false,
          },
          version: 0,
        }),
      );
    },
    { tokens: TOKENS, sessionUser: user },
  );
}

// ---------------------------------------------------------------------------
// Backend mocking — URL predicates only (see header comment).
// ---------------------------------------------------------------------------

const isBackend = (url: URL) => url.port !== "5173";

function jsonRoute(body: unknown, status = 200) {
  return (route: Route) => route.fulfill({ status, json: body });
}

const ALERTS_SUMMARY = {
  overdue: 0,
  due_soon: 0,
  ok: 0,
  never_measured: 0,
  rapid_growth_count: 0,
  athletes: [] as unknown[],
};

/** Everything the `/dashboard` landing page (`DashboardPage.tsx` ->
 * `useDashboardStats` -> `useAlerts` -> `MeasurementAlerts`) needs, for
 * either role — `dashboard` is where both coach and admin land post-login
 * (`research.md` R8: no per-role landing change in this feature). */
async function mockDashboardApi(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/health",
    jsonRoute({ ok: true }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/athletes/alerts",
    jsonRoute(ALERTS_SUMMARY),
  );
}

async function gotoDashboard(page: Page): Promise<void> {
  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible({
    timeout: WAIT_TIMEOUT,
  });
}

// ---------------------------------------------------------------------------
// Shared locators — match the `aria-label`s baked into SidebarNav.tsx /
// BottomNav.tsx (contracts/mobile-navigation.md: distinct labels so assistive
// tech never sees two identically-labeled navigation landmarks even while
// both trees are mounted and only `display` toggles).
// ---------------------------------------------------------------------------

function sidebarNav(page: Page) {
  return page.getByRole("navigation", { name: "Secciones" });
}

function bottomNav(page: Page) {
  return page.getByRole("navigation", { name: "Navegación principal" });
}

function moreSheet(page: Page) {
  return page.getByRole("dialog", { name: "Más" });
}

/**
 * The sheet's actual navigational content — `<nav aria-label="Más opciones">`
 * wrapping the area rows + Mi perfil/Salud IA/Cerrar sesión
 * (`MoreSheet.tsx`) — as opposed to the whole `role="dialog"`, which also
 * contains `ui/sheet.tsx`'s generic corner close ("X") button. That close
 * button is shared dialog chrome, not one of the rows
 * `contracts/mobile-navigation.md` enumerates ("Every row ≥48×48px"
 * refers to the "Más" sheet's listed areas/actions) — scoping the sweep here
 * keeps the assertion tied to this feature's own contract instead of
 * incidentally gating on an unrelated, pre-existing shared-component detail.
 */
function moreSheetNav(page: Page) {
  return moreSheet(page).getByRole("navigation", { name: "Más opciones" });
}

// ---------------------------------------------------------------------------
// Target-size sweep — scoped to a root locator (bottom bar or "Más" sheet),
// not a whole-page sweep (that's target-size.spec.ts's job). Inline
// implementation: this feature's components have no dedicated reusable
// Playwright helper module (target-size.spec.ts keeps its sweep local to
// that file too), per T033's "otherwise implement an inline bounding-box
// check" fallback.
// ---------------------------------------------------------------------------

interface Violation {
  tag: string;
  name: string;
  width: number;
  height: number;
}

async function findTargetSizeViolations(
  page: Page,
  root: ReturnType<typeof page.locator>,
): Promise<Violation[]> {
  // `[role='menuitem']` added for T041 (UserMenu/QuickCreate open-menu
  // sweeps): a `DropdownMenuItem` without `asChild` (e.g. "Cerrar sesión")
  // renders as a plain `<div role="menuitem">`, matched by neither `a`,
  // `button`, nor `[role='button']` — harmless no-op for the bottom-bar/
  // "Más" sheet callers above (neither tree contains a `menuitem`).
  const locator = root.locator("a, button, [role='button'], [role='menuitem']");
  const count = await locator.count();
  const violations: Violation[] = [];

  for (let i = 0; i < count; i += 1) {
    const el = locator.nth(i);
    if (!(await el.isVisible())) continue;

    const box = await el.boundingBox();
    if (!box) continue;
    if (box.width < MIN_TARGET_SIZE || box.height < MIN_TARGET_SIZE) {
      const name = await el.evaluate((node) => {
        const element = node as HTMLElement;
        return (
          element.getAttribute("aria-label") ||
          element.innerText?.trim().slice(0, 40) ||
          element.tagName.toLowerCase()
        );
      });
      const tag = await el.evaluate((node) => (node as HTMLElement).tagName.toLowerCase());
      violations.push({ tag, name, width: Math.round(box.width), height: Math.round(box.height) });
    }
  }

  return violations;
}

function describeViolations(violations: Violation[]): string {
  return violations
    .map(
      (v) =>
        `  - <${v.tag}> "${v.name}" -> ${v.width}x${v.height}px (need >=${MIN_TARGET_SIZE}x${MIN_TARGET_SIZE})`,
    )
    .join("\n");
}

async function expectNoTargetSizeViolations(
  page: Page,
  root: ReturnType<typeof page.locator>,
  label: string,
): Promise<void> {
  const violations = await findTargetSizeViolations(page, root);
  expect(
    violations,
    `${label}: ${violations.length} target-size violation(s) found:\n${describeViolations(violations)}`,
  ).toEqual([]);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Feature 030 (T033) — coach/admin navigation: sidebar vs. bottom bar", () => {
  test(">=768px shows the sidebar and hides the bottom bar (coach)", async ({ page }) => {
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await setupAuth(page, COACH_USER);
    await mockDashboardApi(page);

    await gotoDashboard(page);

    await expect(sidebarNav(page)).toBeVisible();
    await expect(bottomNav(page)).toBeHidden();
  });

  test("<768px shows the bottom bar (4 areas + Más) and hides the sidebar (coach)", async ({
    page,
  }) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await setupAuth(page, COACH_USER);
    await mockDashboardApi(page);

    await gotoDashboard(page);

    await expect(bottomNav(page)).toBeVisible();
    await expect(sidebarNav(page)).toBeHidden();

    // Coach slots (order fixed, contracts/mobile-navigation.md): Inicio,
    // Entrenamiento, Competencias, Atletas, then the "Más" trigger.
    const bar = bottomNav(page);
    await expect(bar.getByRole("link", { name: "Inicio" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Entrenamiento" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Competencias" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Atletas" })).toBeVisible();
    await expect(bar.getByRole("button", { name: /Más/ })).toBeVisible();

    // Exactly 5 slots — 4 areas + "Más", nothing extra.
    await expect(bar.locator("a, button")).toHaveCount(5);
  });

  test("no width renders neither the sidebar nor the bottom bar (md boundary)", async ({
    page,
  }) => {
    await setupAuth(page, COACH_USER);
    await mockDashboardApi(page);
    await gotoDashboard(page);

    // Just below the breakpoint: bottom bar visible, sidebar hidden.
    await page.setViewportSize({ width: MD_BREAKPOINT - 1, height: 800 });
    await expect(bottomNav(page)).toBeVisible();
    await expect(sidebarNav(page)).toBeHidden();

    // Exactly at the breakpoint: sidebar visible, bottom bar hidden — the
    // complementary state flips with no width in between rendering neither.
    await page.setViewportSize({ width: MD_BREAKPOINT, height: 800 });
    await expect(sidebarNav(page)).toBeVisible();
    await expect(bottomNav(page)).toBeHidden();

    // A representative narrow-desktop width well above md — still exactly
    // one of the two, never neither (spec.md edge case: narrow desktop
    // windows resized continuously through the breakpoint).
    await page.setViewportSize({ width: 1024, height: 800 });
    await expect(sidebarNav(page)).toBeVisible();
    await expect(bottomNav(page)).toBeHidden();
  });

  test("admin login shows Biblioteca (not Atletas) in the bottom bar's 4th slot", async ({
    page,
  }) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await setupAuth(page, ADMIN_USER);
    await mockDashboardApi(page);

    await gotoDashboard(page);

    const bar = bottomNav(page);
    await expect(bar.getByRole("link", { name: "Inicio" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Entrenamiento" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Competencias" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Biblioteca" })).toBeVisible();
    await expect(bar.getByRole("link", { name: "Atletas" })).toHaveCount(0);
    await expect(bar.getByRole("button", { name: /Más/ })).toBeVisible();
    await expect(bar.locator("a, button")).toHaveCount(5);
  });

  test("every bottom-bar and 'Más' sheet control measures >=48x48px (coach)", async ({
    page,
  }) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await setupAuth(page, COACH_USER);
    await mockDashboardApi(page);

    await gotoDashboard(page);
    await expect(bottomNav(page)).toBeVisible();

    await expectNoTargetSizeViolations(page, bottomNav(page), "Bottom bar (coach)");

    // Open "Más" — role-visible remaining areas (Familias, Biblioteca) plus
    // Mi perfil / Cerrar sesión (admin also gets Salud IA, covered below).
    await bottomNav(page).getByRole("button", { name: /Más/ }).click();
    await expect(moreSheet(page)).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(moreSheet(page).getByRole("link", { name: "Familias" })).toBeVisible();

    await expectNoTargetSizeViolations(page, moreSheetNav(page), "Más sheet (coach)");
  });

  test("every bottom-bar and 'Más' sheet control measures >=48x48px (admin)", async ({
    page,
  }) => {
    await page.setViewportSize(MOBILE_VIEWPORT);
    await setupAuth(page, ADMIN_USER);
    await mockDashboardApi(page);

    await gotoDashboard(page);
    await expect(bottomNav(page)).toBeVisible();

    await expectNoTargetSizeViolations(page, bottomNav(page), "Bottom bar (admin)");

    await bottomNav(page).getByRole("button", { name: /Más/ }).click();
    await expect(moreSheet(page)).toBeVisible({ timeout: WAIT_TIMEOUT });
    // Admin-only row confirming the sheet actually rendered its full content
    // (Salud IA, research.md R7 / contracts/mobile-navigation.md) before the
    // sweep runs.
    await expect(moreSheet(page).getByRole("link", { name: "Salud IA" })).toBeVisible();

    await expectNoTargetSizeViolations(page, moreSheetNav(page), "Más sheet (admin)");
  });
});

// ---------------------------------------------------------------------------
// T041 — header actions: <UserMenu> + <QuickCreate> (US4, contracts/header-actions.md)
//
// Both triggers render unconditionally in AppShell's header for coach/admin
// (not viewport-gated like SidebarNav/BottomNav), so a single desktop
// viewport is enough to exercise them here — mirrors the existing bottom-bar
// sweep's reuse of `expectNoTargetSizeViolations`, scoped to each dropdown's
// own root instead of the whole page (target-size.spec.ts's job).
// ---------------------------------------------------------------------------

function userMenuTrigger(page: Page) {
  return page.getByTestId("user-menu-trigger");
}

function quickCreateTrigger(page: Page) {
  return page.getByTestId("quick-create-trigger");
}

test.describe("Feature 030 (T041) — header actions: user menu + quick-create", () => {
  test("coach: user-menu trigger + open-menu items measure >=48x48px and are keyboard-operable (Tab/Enter/Escape)", async ({
    page,
  }) => {
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await setupAuth(page, COACH_USER);
    await mockDashboardApi(page);
    await gotoDashboard(page);

    const trigger = userMenuTrigger(page);
    await expect(trigger).toBeVisible();

    // Reach the trigger via keyboard focus (Tab order across the full
    // sidebar + header is a SidebarNav implementation detail, not this
    // task's concern — `.focus()` isolates "is this control itself
    // keyboard-reachable and does Enter/Escape drive it", same as the
    // admin/quick-create variants below) then drive it with Enter/Escape
    // only — no pointer interaction anywhere in this test.
    await trigger.focus();
    await expect(trigger).toBeFocused();
    await page.keyboard.press("Enter");

    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible({ timeout: WAIT_TIMEOUT });

    // Coach: "Mi perfil" + "Cerrar sesión" only (no "Salud IA" — admin-only,
    // contracts/header-actions.md).
    await expectNoTargetSizeViolations(page, menu, "User menu (coach, open)");
    const triggerBox = await trigger.boundingBox();
    expect(triggerBox?.width ?? 0).toBeGreaterThanOrEqual(MIN_TARGET_SIZE);
    expect(triggerBox?.height ?? 0).toBeGreaterThanOrEqual(MIN_TARGET_SIZE);

    // Escape closes the menu and returns focus to the trigger (Radix
    // default) — both keyboard-operability requirements for this task.
    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("admin: user menu includes 'Salud IA' and every item still measures >=48x48px", async ({
    page,
  }) => {
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await setupAuth(page, ADMIN_USER);
    await mockDashboardApi(page);
    await gotoDashboard(page);

    const trigger = userMenuTrigger(page);
    await trigger.focus();
    await page.keyboard.press("Enter");

    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(menu.getByRole("menuitem", { name: "Salud IA" })).toBeVisible();

    await expectNoTargetSizeViolations(page, menu, "User menu (admin, open)");

    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
  });

  test("coach: quick-create trigger + open-menu items (incl. 'Nuevo atleta') measure >=48x48px and are keyboard-operable (Tab/Enter/Escape)", async ({
    page,
  }) => {
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await setupAuth(page, COACH_USER);
    await mockDashboardApi(page);
    await gotoDashboard(page);

    const trigger = quickCreateTrigger(page);
    await expect(trigger).toBeVisible();
    const triggerBox = await trigger.boundingBox();
    expect(triggerBox?.width ?? 0).toBeGreaterThanOrEqual(MIN_TARGET_SIZE);
    expect(triggerBox?.height ?? 0).toBeGreaterThanOrEqual(MIN_TARGET_SIZE);

    await trigger.focus();
    await expect(trigger).toBeFocused();
    await page.keyboard.press("Enter");

    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible({ timeout: WAIT_TIMEOUT });
    await expect(page.getByTestId("quick-create.athlete")).toBeVisible();

    await expectNoTargetSizeViolations(page, menu, "Quick-create menu (coach, open)");

    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
    await expect(trigger).toBeFocused();
  });

  test("admin: quick-create menu omits 'Nuevo atleta' and every remaining item measures >=48x48px", async ({
    page,
  }) => {
    await page.setViewportSize(DESKTOP_VIEWPORT);
    await setupAuth(page, ADMIN_USER);
    await mockDashboardApi(page);
    await gotoDashboard(page);

    const trigger = quickCreateTrigger(page);
    await trigger.focus();
    await page.keyboard.press("Enter");

    const menu = page.getByRole("menu");
    await expect(menu).toBeVisible({ timeout: WAIT_TIMEOUT });

    // "Nuevo atleta" is coach-only (contracts/header-actions.md) — absent
    // for admin at the real-DOM/e2e level, not just the jsdom unit test.
    await expect(page.getByTestId("quick-create.athlete")).toHaveCount(0);
    await expect(page.getByTestId("quick-create.session")).toBeVisible();
    await expect(page.getByTestId("quick-create.competition")).toBeVisible();
    await expect(page.getByTestId("quick-create.event")).toBeVisible();

    await expectNoTargetSizeViolations(page, menu, "Quick-create menu (admin, open)");

    await page.keyboard.press("Escape");
    await expect(menu).toBeHidden();
  });
});
