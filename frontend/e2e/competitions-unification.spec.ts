/**
 * E2E de la unificación `/competitions` + Análisis IA (PR1→PR7).
 * Workflow: docs/12-competitions-unification/workflow.md
 *
 * A diferencia de los specs de calendar/newsletters (que mockean el backend
 * con `page.route`), este spec corre contra el STACK REAL ya levantado:
 *   - Backend FastAPI real en http://localhost:8000 (Docker, MySQL sembrado)
 *   - Frontend Vite real en http://localhost:5173 con
 *     VITE_INSIGHTS_IN_COMPETITION=true (flag PR2 ON)
 *
 * Login: vía formulario (mismo patrón que auth.spec.ts), con credenciales
 * seed reales. El token queda en sessionStorage['auth-session'].
 *
 * Estado del árbol = FINAL (PR7): las rutas legacy NO redirigen 301; muestran
 * GonePage (equivalente SPA de 410). El tab `insights` del detalle monta el
 * módulo IA (strangler) porque el flag está ON.
 *
 * Privacidad: NO se hardcodean nombres de menores. Los asserts son
 * estructurales (data-testid, headings, roles) o sobre agregados.
 *
 * Cobertura de los 9 escenarios cubribles con el seed actual + 2 skips
 * documentados (PR4 diff dropdown, PR5 stale badge) cuyo prerequisito de datos
 * no existe en el seed.
 */
import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Credenciales seed reales (entorno dev/Docker — NUNCA producción)
// ---------------------------------------------------------------------------

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const PARENT = { email: "padre@trochayruta.com", password: "Parent2026!" };

// Datos seed (deep-links). race_event id 5 = Válida IV Cali (completed),
// con 4 atletas con club-insights y temporada 2026 con 5 atletas en panorama.
const COMPLETED_RACE_ID = 5;
const SEASON_YEAR = 2026;

// El primer request tras el cold-start del backend puede tardar (~50s en free
// tier; aquí es Docker local pero la primera query a MySQL + arranque de
// pools puede ser lenta). Timeout generoso para el login y la 1ª navegación.
const COLD_START_TIMEOUT = 90_000;
const NAV_TIMEOUT = 30_000;

// ---------------------------------------------------------------------------
// Helpers de login (patrón de auth.spec.ts — login real vía UI)
// ---------------------------------------------------------------------------

async function login(
  page: Page,
  creds: { email: string; password: string },
): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(creds.email);
  await page.getByRole("textbox", { name: /contraseña/i }).fill(creds.password);
  await page.getByRole("button", { name: /ingresar/i }).click();

  // Tras login exitoso, el store deja la sesión en sessionStorage y
  // redirige fuera de /login. Esperamos la transición con timeout amplio
  // para tolerar el cold-start del backend en el primer POST /auth/login.
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

async function loginAsCoach(page: Page): Promise<void> {
  await login(page, COACH);
}

async function loginAsParent(page: Page): Promise<void> {
  await login(page, PARENT);
}

// ---------------------------------------------------------------------------
// PR7 — GonePage (rutas legacy deprecadas, equivalente 410)
// ---------------------------------------------------------------------------

test.describe("Unificación competencias — PR7 GonePage", () => {
  test("E2E-CU-001: coach en /coach/race-analysis ve GonePage y el link lleva al índice de análisis", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/coach/race-analysis");

    // GonePage montada (no redirige 301: el árbol está en estado FINAL/PR7).
    const gone = page.getByTestId("gone-page");
    await expect(gone).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(
      page.getByRole("heading", { name: /esta sección se movió/i }),
    ).toBeVisible();

    // El link "Ir a Análisis IA" navega al nuevo hub /competitions/insights.
    const link = page.getByRole("link", { name: /ir a análisis ia/i });
    await expect(link).toBeVisible();
    await link.click();

    await expect(page).toHaveURL(/\/competitions\/insights$/, {
      timeout: NAV_TIMEOUT,
    });
    // Aterriza en el índice slim (InsightsHubPage), no en otra GonePage.
    await expect(
      page.getByRole("heading", { name: /análisis ia carreras/i }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("hub-card-season")).toBeVisible();
  });

  test("E2E-CU-002: coach en /training/races/:id/club-insights ve GonePage", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/training/races/${COMPLETED_RACE_ID}/club-insights`);

    await expect(page.getByTestId("gone-page")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(
      page.getByRole("heading", { name: /esta sección se movió/i }),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// PR1/PR3 — Hub y subpáginas IA cross-válida (datos reales del backend)
// ---------------------------------------------------------------------------

test.describe("Unificación competencias — hub y vistas IA", () => {
  test("E2E-CU-003: coach abre /competitions/insights y ve el índice slim (Season + Club)", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/insights");

    // Tras eliminar el hub de 5 tabs, /competitions/insights monta
    // InsightsHubPage: índice read-only con header + 2 accesos.
    await expect(
      page.getByRole("heading", { name: /análisis ia carreras/i }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // Acceso 1: Panorama de temporada → season del año actual.
    const seasonCard = page.getByTestId("hub-card-season");
    await expect(seasonCard).toBeVisible();
    await expect(seasonCard).toHaveAttribute(
      "href",
      `/competitions/insights/season/${SEASON_YEAR}`,
    );

    // Acceso 2: Análisis por válida → /competitions/insights/club.
    const clubCard = page.getByTestId("hub-card-club");
    await expect(clubCard).toBeVisible();
    await expect(clubCard).toHaveAttribute(
      "href",
      "/competitions/insights/club",
    );

    // El hub viejo (lanzador/chat/import) ya NO existe: sin tabs de módulo IA.
    await expect(page.getByRole("tab", { name: /nuevo análisis/i })).toHaveCount(0);
    await expect(page.getByRole("tab", { name: /cargar resultados/i })).toHaveCount(0);

    // No quedó atrapado en la GonePage ni en NotFound.
    await expect(page.getByTestId("gone-page")).toHaveCount(0);

    // El acceso a "Análisis por válida" navega correctamente al subíndice club.
    await clubCard.click();
    await expect(page).toHaveURL(/\/competitions\/insights\/club$/, {
      timeout: NAV_TIMEOUT,
    });
    await expect(
      page.getByRole("heading", { name: /análisis del club por válida/i }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
  });

  test("E2E-CU-004: coach abre /competitions/insights/season/:year y la tabla carga datos reales", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/competitions/insights/season/${SEASON_YEAR}`);

    // Header de la página.
    await expect(
      page.getByRole("heading", {
        name: new RegExp(`panorama de temporada ${SEASON_YEAR}`, "i"),
      }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // El endpoint real GET /api/race-analysis/insights/season/2026 devuelve
    // >0 atletas para el seed → debe renderizar la tabla agregada (no el
    // estado vacío ni el de error).
    await expect(page.getByTestId("season-insights-table")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(page.getByTestId("season-insights-error")).toHaveCount(0);

    // Hay al menos una fila de deportista (selector estructural, sin asumir
    // nombres). Las filas usan data-testid `season-row-{athleteId}`.
    const rows = page.locator('[data-testid^="season-row-"]');
    await expect(rows.first()).toBeVisible();
    expect(await rows.count()).toBeGreaterThan(0);
  });

  test("E2E-CU-005: coach abre /competitions/insights/club y la página carga", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/insights/club");

    await expect(
      page.getByRole("heading", { name: /análisis del club por válida/i }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // El selector de válida se monta y se rellena desde
    // GET /api/race-analysis/race-events/ (el seed tiene válidas).
    const select = page.getByTestId("club-insights-race-select");
    await expect(select).toBeVisible({ timeout: NAV_TIMEOUT });

    // No cae en "no hay válidas" (el seed tiene race_events). Esperamos que
    // termine de cargar mostrando el grid de insights o el estado "sin
    // insights" — pero NUNCA un error de carga.
    await expect(page.getByTestId("club-insights-no-races")).toHaveCount(0);
    await expect
      .poll(
        async () => {
          const grid = await page
            .getByTestId("club-insights-grid")
            .count();
          const empty = await page
            .getByTestId("club-insights-empty")
            .count();
          const error = await page
            .getByTestId("club-insights-error")
            .count();
          // -1 = error (no aceptable), 1 = resuelto (grid o empty), 0 = aún cargando
          if (error > 0) return -1;
          return grid > 0 || empty > 0 ? 1 : 0;
        },
        { timeout: NAV_TIMEOUT },
      )
      .toBe(1);
  });
});

// ---------------------------------------------------------------------------
// Tab `insights` del detalle — grid scopeado por válida (strangler eliminado)
// ---------------------------------------------------------------------------

test.describe("Unificación competencias — tab insights scopeado", () => {
  test("E2E-CU-006: /competitions/:id?tab=insights monta el grid scopeado a la válida (sin módulo IA global)", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/competitions/${COMPLETED_RACE_ID}?tab=insights`);

    // El detalle carga (header de la competencia).
    await expect(page.getByTestId("competition-title")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // Tras eliminar el strangler `VITE_INSIGHTS_IN_COMPETITION`, el tab SIEMPRE
    // renderiza ClubInsightsGrid scopeado a la válida → data-testid="insights-tab".
    // El wrapper viejo del módulo IA global ("insights-tab-module") ya NO existe.
    await expect(page.getByTestId("insights-tab")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(page.getByTestId("insights-tab-module")).toHaveCount(0);

    // Defensa: el grid scopeado NO monta el hub global (sin tabs "Nuevo análisis"
    // / "Cargar resultados", sin heading "Análisis de carreras").
    await expect(page.getByRole("tab", { name: /nuevo análisis/i })).toHaveCount(0);
    await expect(
      page.getByRole("heading", { name: /análisis de carreras/i }),
    ).toHaveCount(0);

    // La válida 5 (Cali) tiene insights de club en el seed → el grid muestra
    // al menos una card por atleta (selector estructural, sin asumir nombres).
    const cards = page.locator('[data-testid^="insights-tab-card-"]');
    await expect(cards.first()).toBeVisible({ timeout: NAV_TIMEOUT });
    expect(await cards.count()).toBeGreaterThan(0);
  });
});

// ---------------------------------------------------------------------------
// RBAC — parent NO accede a las vistas IA (D2: parents → redirect)
// ---------------------------------------------------------------------------

test.describe("Unificación competencias — RBAC parent", () => {
  test("E2E-CU-007: parent en /competitions/insights es redirigido a /my-athletes", async ({
    page,
  }) => {
    await loginAsParent(page);

    await page.goto("/competitions/insights");

    // ProtectedRoute(coach/admin) → parent cae a su landing /my-athletes.
    await expect(page).toHaveURL(/\/my-athletes$/, { timeout: NAV_TIMEOUT });

    // No se expone el índice de análisis: ni su heading ni sus accesos
    // (hub-card-*) deben estar presentes para el padre.
    await expect(
      page.getByRole("heading", { name: /análisis ia carreras/i }),
    ).toHaveCount(0);
    await expect(page.getByTestId("hub-card-season")).toHaveCount(0);
    await expect(page.getByTestId("hub-card-club")).toHaveCount(0);
  });

  test("E2E-CU-008: parent en /competitions/insights/season/:year es redirigido a /my-athletes", async ({
    page,
  }) => {
    await loginAsParent(page);

    await page.goto(`/competitions/insights/season/${SEASON_YEAR}`);

    await expect(page).toHaveURL(/\/my-athletes$/, { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("season-insights-table")).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// PR6 — Checkbox "Crear evento en calendario" (D1: ON por default)
// ---------------------------------------------------------------------------

test.describe("Unificación competencias — PR6 checkbox calendario", () => {
  test("E2E-CU-009: el form de nueva competencia tiene el checkbox de calendario marcado por default", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/new");

    // El form carga (heading "Nueva competencia").
    await expect(
      page.getByRole("heading", { name: /nueva competencia/i }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // D1: checkbox presente y marcado por default (opt-out visible).
    const checkbox = page.getByTestId("create-calendar-event-checkbox");
    await expect(checkbox).toBeVisible();
    await expect(checkbox).toBeChecked();
  });
});

// ---------------------------------------------------------------------------
// Sidebar — entrada única "Análisis IA" → /competitions/insights, sin legacy
// ---------------------------------------------------------------------------

test.describe("Unificación competencias — sidebar único", () => {
  test("E2E-CU-010: el sidebar del coach muestra Competencias + Análisis IA hacia el hub, sin link a /coach/race-analysis", async ({
    page,
  }) => {
    await loginAsCoach(page);

    // Aterrizamos en una ruta autenticada cualquiera (dashboard) para tener
    // el AppShell montado.
    await page.goto("/dashboard");
    await expect(page.getByRole("navigation").first()).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // Entrada "Competencias" → /competitions.
    const competenciasLink = page.getByRole("link", { name: /^competencias$/i });
    await expect(competenciasLink).toBeVisible();
    await expect(competenciasLink).toHaveAttribute("href", "/competitions");

    // Entrada "Análisis IA carreras" → /competitions/insights (hub unificado).
    const insightsLink = page.getByRole("link", {
      name: /análisis ia carreras/i,
    });
    await expect(insightsLink).toBeVisible();
    await expect(insightsLink).toHaveAttribute(
      "href",
      "/competitions/insights",
    );

    // NO debe existir NINGÚN link a la ruta legacy /coach/race-analysis.
    await expect(
      page.locator('a[href="/coach/race-analysis"]'),
    ).toHaveCount(0);

    // Y al hacer click en "Análisis IA carreras" aterriza en el hub.
    await insightsLink.click();
    await expect(page).toHaveURL(/\/competitions\/insights$/, {
      timeout: NAV_TIMEOUT,
    });
  });
});

// ---------------------------------------------------------------------------
// PR4 / PR5 — requieren estado que el seed actual NO provee. Skips documentados.
// ---------------------------------------------------------------------------

test.describe("Unificación competencias — PR4/PR5 (prerequisitos de datos)", () => {
  // PR4: el dropdown de catálogo `revision_reason` (data-testid
  // "wizard-revision-reason") SOLO se renderiza cuando el dry-run del wizard
  // devuelve `is_revision: true`. Eso ocurre únicamente tras una re-ingesta
  // sobre un race_event con un import previo (SHA256 distinto). El seed no
  // tiene un import committeado para estas válidas, y no hay PDF fixture en
  // este entorno e2e, así que no podemos provocar el modo revisión sin
  // fabricar datos. Se cubre en los tests unitarios de ImportWizard (vitest).
  test.skip("E2E-CU-011: PR4 dropdown revision_reason aparece en modo revisión [prereq: re-ingesta con import previo + PDF fixture]", async () => {
    // Prerequisito no disponible en el seed: import previo committeado para
    // el mismo race_event_id + segundo PDF con SHA256 distinto que dispare
    // diff_summary con n_delete>0 (que es cuando el motivo es obligatorio).
  });

  // PR5: el badge "Análisis desactualizado" (data-testid
  // "stale-analysis-badge") SOLO se renderiza junto a un run/insight cuyo
  // `stale_since` no es null. El seed tiene 48 agent_runs pero ninguno está
  // marcado stale (no hubo re-ingesta que invalide un run). Además el badge
  // se monta dentro de AthleteAIAnalysisTab (perfil del deportista), no en
  // las rutas /competitions/insights/* que cubre este spec. Forzarlo
  // requeriría: (1) un run aprobado para un atleta, (2) una re-ingesta que
  // dispare POST /runs/{id}/invalidate y poble stale_since. Se cubre en los
  // tests unitarios de StaleAnalysisBadge (vitest).
  test.skip("E2E-CU-012: PR5 badge 'Análisis desactualizado' + re-ejecutar [prereq: run con stale_since != null]", async () => {
    // Prerequisito no disponible en el seed: agent_run con stale_since
    // poblado (requiere re-ingesta previa que invalide el run).
  });
});
