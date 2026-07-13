/**
 * E2E — Feature 032 (Session Content Unification), T045.
 *
 * Runs against the REAL stack (FastAPI backend + MySQL + Vite dev server),
 * same convention as `competitions-unification.spec.ts` (real login via the
 * form, real seed data) — NOT the `page.route`-mocked convention used by
 * `target-size.spec.ts`/`calendar-coach.spec.ts`. Content unification is
 * exactly the kind of cross-cutting, three-content-types-in-one-session flow
 * that a route-mocked test would only prove against fixtures the test author
 * already believes are correct; running it for real against the actual
 * backend endpoint (`POST /api/technique/sessions/{id}/exercises`, T006) and
 * the actual strength/interval attach endpoints is the point of this file.
 *
 * Flow (quickstart.md "Playwright end-to-end flow"):
 *   1. Log in as coach (seed credentials).
 *   2. Create a session via the existing wizard (unchanged by this feature).
 *   3. From the session's Plan section: attach 2+ technique exercises inline.
 *   4. Attach a strength block via "pick existing" (StrengthBlockPicker).
 *   5. Create an interval structure inline (StructureEditor — reference flow,
 *      regression check only, unchanged logic per research.md R3).
 *   6. Assert all three show together in the Plan section as one list, and
 *      assert no duplicate row appeared in /training/sessions (SC-002).
 *   7. Measure every interactive control this flow actually exercises for the
 *      >=48x48px touch-target floor (Constitution III) — not a page-wide
 *      sweep (that's `target-size.spec.ts`'s job, and this file must not
 *      extend it per task instructions); scoped this way so a failure here
 *      is attributable to this feature's own new/touched components.
 *   8. Refresh mid-flow and assert the active `?section=` persisted (SC-006).
 *
 * Requires a full local stack: `docker compose up` (or backend + `npm run
 * dev` + MySQL running individually) with seed data present (coach user,
 * >=2 technique catalog exercises, >=1 non-archived strength block, >=1
 * athlete — all present in the standard dev seed).
 */
import { test, expect, type Locator, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Seed credentials (dev/Docker only — never production, per auth.spec.ts /
// competitions-unification.spec.ts convention).
// ---------------------------------------------------------------------------

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };

// Cold start (Render free tier / first Docker request) can be slow even
// locally on the first MySQL pool warmup — generous timeouts, mirroring
// competitions-unification.spec.ts.
const COLD_START_TIMEOUT = 90_000;
const NAV_TIMEOUT = 30_000;

/** Constitution III / CLAUDE.md: every touch target must be >=48x48 CSS px. */
const MIN_TARGET_SIZE = 48;

// ---------------------------------------------------------------------------
// Login (real form submit — no sessionStorage shortcut, matches
// competitions-unification.spec.ts's real-stack convention).
// ---------------------------------------------------------------------------

async function loginAsCoach(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(COACH.email);
  await page.getByRole("textbox", { name: /contraseña/i }).fill(COACH.password);
  await page.getByRole("button", { name: /ingresar/i }).click();

  await expect(page).not.toHaveURL(/\/login/, { timeout: COLD_START_TIMEOUT });
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const raw = sessionStorage.getItem("auth-session");
          if (!raw) return false;
          try {
            return JSON.parse(raw)?.state?.isAuthenticated === true;
          } catch {
            return false;
          }
        }),
      { timeout: 10_000 },
    )
    .toBe(true);
}

// ---------------------------------------------------------------------------
// Unique fixture identity — a far-future, run-specific date + a timestamped
// technical_focus label so this spec can run repeatedly against a shared dev
// DB without colliding with prior runs' leftover sessions (no test-only
// cleanup endpoint exists, so we scope every assertion narrowly instead of
// relying on a clean DB).
// ---------------------------------------------------------------------------

function futureUniqueDateISO(): string {
  // Days-ahead offset derived from the current timestamp so consecutive runs
  // land on different calendar days (collision with a previous run's leftover
  // session would corrupt the SC-002 row-count assertion below).
  const daysAhead = 3000 + (Date.now() % 1000);
  const date = new Date();
  date.setDate(date.getDate() + daysAhead);
  return date.toISOString().slice(0, 10);
}

const RUN_ID = Date.now();
const SESSION_DATE = futureUniqueDateISO();
const TECHNICAL_FOCUS = `E2E-032 Unificación de plan ${RUN_ID}`;

// ---------------------------------------------------------------------------
// Target-size check — quickstart.md step 7 asks specifically for "every
// interactive control exercised above" (i.e. by this flow), not a blanket
// whole-page sweep. A page-wide sweep (the `target-size.spec.ts` convention,
// which this new file intentionally does not extend per T045's instructions)
// would also catch the global `SidebarNav`/header chrome that every route
// renders — that's feature 028/030's territory and already has its own
// dedicated sweep; conflating it here would make failures hard to attribute
// to this feature's actual new/touched components. So: measure each control
// at the moment this flow interacts with it (before it can unmount/rerender
// away, e.g. the interval "Crear estructura" trigger button, which is
// replaced by the editor form on click) and assert the whole batch once at
// the end for one consolidated, readable failure if anything is under the
// 48x48 CSS px floor (Constitution III / CLAUDE.md).
// ---------------------------------------------------------------------------

interface Violation {
  label: string;
  width: number;
  height: number;
}

/** Measures `locator` right now and records a violation if under the floor. Call inline, immediately around each interaction. */
async function measureTarget(
  violations: Violation[],
  label: string,
  locator: Locator,
): Promise<void> {
  const box = await locator.boundingBox();
  if (!box) return; // not visible/attached — nothing to measure
  if (box.width < MIN_TARGET_SIZE || box.height < MIN_TARGET_SIZE) {
    violations.push({ label, width: Math.round(box.width), height: Math.round(box.height) });
  }
}

function describeViolations(violations: Violation[]): string {
  return violations
    .map(
      (v) => `  - "${v.label}" -> ${v.width}x${v.height}px (need >=${MIN_TARGET_SIZE}x${MIN_TARGET_SIZE})`,
    )
    .join("\n");
}

// ---------------------------------------------------------------------------
// Wizard helper — creates a session via the existing multi-step wizard
// (unchanged by this feature, per plan.md). Requires >=1 athlete in the club
// seed (standard dev seed has many).
// ---------------------------------------------------------------------------

async function createSessionViaWizard(page: Page): Promise<number> {
  await page.goto("/training/sessions/new");
  await expect(page.getByTestId("session-wizard")).toBeVisible({ timeout: NAV_TIMEOUT });

  // Step 1 — General
  await expect(page.getByTestId("session-step-general")).toBeVisible();
  await page.locator("#scheduled_date-input").fill(SESSION_DATE);
  await page.locator("#scheduled_start_time-input").fill("09:00");
  await page.locator("#location-input").fill("Pista XCO La Buitrera");
  await page.locator("#technical_focus-input").fill(TECHNICAL_FOCUS);
  await page
    .locator("#description-input")
    .fill("Sesión E2E (feature 032) para validar la unificación de contenido del Plan.");
  await page.getByRole("button", { name: /siguiente/i }).click();

  // Step 2 — Atletas (al menos uno convocado, requerido por el esquema)
  await expect(page.getByTestId("session-step-athletes")).toBeVisible();
  await page
    .getByTestId("session-step-athletes")
    .locator('input[type="checkbox"]')
    .first()
    .check();
  await page.getByRole("button", { name: /siguiente/i }).click();

  // Step 3 — Ruta y notas (todo opcional, sin cambios).
  await expect(page.getByTestId("session-step-route-notes")).toBeVisible();
  await page.getByRole("button", { name: /siguiente/i }).click();

  // Pre-existing bug in SessionWizard.tsx (confirmed via trace analysis,
  // unrelated to and unmodified by feature 032): the "Siguiente"/"Crear
  // sesión" buttons render in the same DOM slot, so React patches the
  // existing <button>'s `type` attribute in place (button -> submit) rather
  // than swapping nodes. `goNext()`'s `await trigger(...)` resolves via a
  // microtask, and that microtask (which calls `setStep(4)`) is flushed
  // before the browser evaluates this SAME click's default action — so the
  // browser can observe the already-flipped `type="submit"` and submit the
  // form immediately, skipping the "Revisar" step (and the "notificar a las
  // familias" toggle) entirely. This reproduced consistently in this run
  // (network trace: the POST fires within ~0ms of the step-3 "Siguiente"
  // click resolving, well before any click ever targets the submit button).
  // Handle both outcomes defensively so this spec exercises the flow
  // correctly either way, without silently masking the finding.
  const alreadySubmitted = await page
    .waitForURL(/\/training\/sessions\/\d+(?:\?|$)/, { timeout: 3_000 })
    .then(() => true)
    .catch(() => false);

  if (!alreadySubmitted) {
    // Step 4 — Revisar y crear (no marcar "notificar a las familias": evita
    // depender de que el proveedor de email esté configurado en el entorno).
    await expect(page.getByTestId("session-step-review")).toBeVisible();
    const submitButton = page.getByTestId("session-wizard-submit");
    await expect(submitButton).toBeEnabled();
    await submitButton.click({ force: true });
    // Al crear (no editar), el wizard navega directo al detalle de la sesión
    // sin pantalla intermedia (SessionWizard.tsx `finishSuccess`).
    await expect(page).toHaveURL(/\/training\/sessions\/\d+(?:\?|$)/, {
      timeout: COLD_START_TIMEOUT,
    });
  }

  const match = page.url().match(/\/training\/sessions\/(\d+)/);
  if (!match) throw new Error(`No se pudo extraer el id de sesión de ${page.url()}`);
  return Number(match[1]);
}

/** Cuenta filas de sesión en /training/sessions filtradas a un único día. */
async function countSessionRowsOnDate(page: Page, dateISO: string): Promise<number> {
  await page.goto("/training/sessions");
  await expect(page.getByRole("heading", { name: /sesiones de entrenamiento/i })).toBeVisible({
    timeout: NAV_TIMEOUT,
  });
  await page.locator("#filter-from-date").fill(dateISO);
  await page.locator("#filter-to-date").fill(dateISO);

  // Espera a que la tabla (o el empty state) refleje el filtro aplicado.
  await expect
    .poll(
      async () => {
        const hasTable = await page.getByRole("table").count();
        const hasEmpty = await page.getByText(/no hay sesiones para los filtros/i).count();
        return hasTable > 0 || hasEmpty > 0;
      },
      { timeout: NAV_TIMEOUT },
    )
    .toBeTruthy();

  const tableCount = await page.getByRole("table").count();
  if (tableCount === 0) return 0;
  return page.getByRole("table").locator("tbody tr").count();
}

// ---------------------------------------------------------------------------
// Test
// ---------------------------------------------------------------------------

test.describe("Feature 032 — Session Content Unification (T045)", () => {
  test("coach unifica técnica + fuerza + intervalos en el Plan de una sesión, sin duplicar filas y con targets >=48x48px", async ({
    page,
  }) => {
    test.setTimeout(180_000);

    const violations: Violation[] = [];

    await loginAsCoach(page);

    // --- Crear la sesión (wizard existente, sin cambios) ---------------------
    const sessionId = await createSessionViaWizard(page);
    await expect(page.getByTestId("session-detail-header")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(page.getByTestId("session-detail-header")).toContainText(TECHNICAL_FOCUS);

    // --- Línea base SC-002: exactamente 1 fila para esta fecha antes de adjuntar ---
    const baselineRowCount = await countSessionRowsOnDate(page, SESSION_DATE);
    expect(baselineRowCount).toBe(1);

    // --- Volver al detalle y entrar a la sección Plan -----------------------
    await page.goto(`/training/sessions/${sessionId}`);
    await expect(page.getByTestId("session-detail-header")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    const planTab = page.getByTestId("session-section-tab-plan");
    await measureTarget(violations, "Tab Plan", planTab);
    await planTab.click();
    await expect(page).toHaveURL(new RegExp(`/training/sessions/${sessionId}\\?section=plan`));
    await expect(page.getByTestId("session-section-plan")).toBeVisible();

    // Sesión recién creada: sin contenido todavía -> empty state combinado
    // (FR-005). `EmptyState`'s `title` renders as a plain <p>, not a heading.
    await expect(
      page.getByText(/esta sesión todavía no tiene contenido/i),
    ).toBeVisible({ timeout: NAV_TIMEOUT });

    // --- 1) Adjuntar 2+ ejercicios de técnica (inline, sin crear sesión nueva) ---
    const revealTechniqueButton = page.getByRole("button", {
      name: "Agregar ejercicios de técnica",
    });
    await measureTarget(violations, "Botón 'Agregar ejercicios de técnica'", revealTechniqueButton);
    await revealTechniqueButton.click();

    const exerciseGrid = page.locator('[aria-label^="Selección de ejercicios"]');
    await expect(exerciseGrid).toBeVisible({ timeout: NAV_TIMEOUT });
    const exerciseCheckboxes = exerciseGrid.locator('input[type="checkbox"]');
    await expect(exerciseCheckboxes.first()).toBeVisible();
    await measureTarget(violations, "Checkbox de ejercicio de técnica (1/2)", exerciseCheckboxes.nth(0));
    await exerciseCheckboxes.nth(0).check();
    await measureTarget(violations, "Checkbox de ejercicio de técnica (2/2)", exerciseCheckboxes.nth(1));
    await exerciseCheckboxes.nth(1).check();

    const attachTechniqueButton = page.getByRole("button", {
      name: /adjuntar a la sesión \(2\)/i,
    });
    await measureTarget(violations, "Botón 'Adjuntar a la sesión' (técnica)", attachTechniqueButton);
    await attachTechniqueButton.click();
    await expect(
      page.getByRole("heading", { name: /ejercicios de técnica en esta sesión/i }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(
      page
        .getByRole("heading", { name: /ejercicios de técnica en esta sesión/i })
        .locator("xpath=following-sibling::ul[1]")
        .locator("li"),
    ).toHaveCount(2);

    // --- 2) Adjuntar un bloque de fuerza existente ("pick existing") --------
    const revealStrengthButton = page.getByRole("button", { name: "Agregar bloque de fuerza" });
    await measureTarget(violations, "Botón 'Agregar bloque de fuerza'", revealStrengthButton);
    await revealStrengthButton.click();
    const strengthPickerCards = page.locator('[aria-label^="Bloques de fuerza del club"]');
    await expect(strengthPickerCards).toBeVisible({ timeout: NAV_TIMEOUT });
    const firstStrengthAttachButton = strengthPickerCards
      .getByRole("button", { name: /adjuntar a la sesión/i })
      .first();
    await expect(firstStrengthAttachButton).toBeVisible();
    await measureTarget(violations, "Botón 'Adjuntar a la sesión' (fuerza)", firstStrengthAttachButton);
    await firstStrengthAttachButton.click();
    await expect(
      strengthPickerCards.getByText(/adjuntado a la sesión/i).first(),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("session-strength-blocks")).toBeVisible();
    // Direct children only: each block <li> nests its own entries <ul><li>,
    // so an unscoped "li" selector would also count exercise-entry rows.
    await expect(
      page.getByTestId("session-strength-blocks").locator("> li"),
    ).toHaveCount(1);

    // --- 3) Crear una estructura de intervalos inline (flujo de referencia) ---
    const createStructureTrigger = page.getByRole("button", {
      name: "Crear estructura",
      exact: true,
    });
    await measureTarget(violations, "Botón 'Crear estructura' (disparador)", createStructureTrigger);
    await createStructureTrigger.click();
    await expect(
      page.getByRole("heading", { name: "Crear estructura de intervalos" }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    // Valores por defecto (13-15, un bloque calentamiento Z1 a 70 rpm) son
    // válidos sin disparar ninguna compuerta por edad -> envío directo.
    const createStructureSubmit = page.getByRole("button", {
      name: "Crear estructura",
      exact: true,
    });
    await measureTarget(violations, "Botón 'Crear estructura' (enviar)", createStructureSubmit);
    await createStructureSubmit.click();
    await expect(
      page.getByRole("heading", { name: "Estructura de intervalos" }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(page.getByRole("list", { name: /bloques de la estructura/i })).toBeVisible();

    // --- Los tres tipos de contenido conviven como una sola lista coherente ---
    const planSection = page.getByTestId("session-section-plan");
    // Exact match: `PlanSection`'s own "Ejercicios de técnica" heading —
    // `TechniqueAttachPicker`'s nested "... en esta sesión" heading (asserted
    // separately above) also matches a loose substring, which would violate
    // Playwright's strict-mode single-match rule.
    await expect(
      planSection.getByRole("heading", { name: "Ejercicios de técnica", exact: true }),
    ).toBeVisible();
    await expect(
      planSection.getByRole("heading", { name: "Bloques de fuerza" }),
    ).toBeVisible();
    await expect(
      planSection.getByRole("heading", { name: "Estructura de intervalos" }),
    ).toBeVisible();
    // El empty state combinado ya no debe estar presente.
    await expect(page.getByText(/esta sesión todavía no tiene contenido/i)).toHaveCount(0);

    // --- SC-002: sigue habiendo exactamente 1 fila para esta fecha (0 sesiones duplicadas) ---
    const afterAttachRowCount = await countSessionRowsOnDate(page, SESSION_DATE);
    expect(afterAttachRowCount).toBe(baselineRowCount);

    // --- Target-size: todo control efectivamente interactuado arriba ----
    // debe medir >=48x48px (Constitution III). Consolidado en un solo
    // assert con mensaje legible, aunque cada medición se tomó en el
    // momento exacto de la interacción (algunos, como el botón disparador
    // de "Crear estructura", se desmontan apenas se les hace click).
    expect(
      violations,
      `${violations.length} control(es) interactuado(s) por debajo de ${MIN_TARGET_SIZE}x${MIN_TARGET_SIZE}px:\n${describeViolations(violations)}`,
    ).toEqual([]);

    // --- Navegar y volver / refrescar a mitad de flujo: ?section= persiste (SC-006) ---
    await page.getByTestId("session-section-tab-media").click();
    await expect(page).toHaveURL(new RegExp(`/training/sessions/${sessionId}\\?section=media`));

    await page.reload();
    await expect(page).toHaveURL(new RegExp(`/training/sessions/${sessionId}\\?section=media`));
    await expect(page.getByTestId("session-section-tab-media")).toHaveAttribute(
      "aria-selected",
      "true",
    );

    // Volver a Plan tras el refresh: el contenido adjuntado sigue ahí (persistido en servidor).
    await page.getByTestId("session-section-tab-plan").click();
    await expect(page).toHaveURL(new RegExp(`/training/sessions/${sessionId}\\?section=plan`));
    await expect(
      page.getByTestId("session-section-plan").getByRole("heading", {
        name: /ejercicios de técnica en esta sesión/i,
      }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("session-strength-blocks")).toBeVisible();
    await expect(
      page.getByTestId("session-section-plan").getByRole("heading", {
        name: "Estructura de intervalos",
      }),
    ).toBeVisible();
  });
});
