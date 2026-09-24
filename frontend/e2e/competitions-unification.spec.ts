/**
 * E2E de la unificación `/competitions` — un solo lugar para las competencias
 * (feature 045, T064; antes «PR1→PR7» de la unificación con Análisis IA).
 * Workflow: docs/12-competitions-unification/workflow.md
 * Contratos: specs/045-competitions-one-place/contracts/ui-routes.md y ui-copy.md
 *
 * A diferencia de los specs de calendar/newsletters (que mockean el backend
 * con `page.route`), este spec corre contra el STACK REAL ya levantado:
 *   - Backend FastAPI real en http://localhost:8000 (Docker, MySQL sembrado)
 *   - Frontend Vite real en http://localhost:5173
 *
 * Login: vía formulario (mismo patrón que auth.spec.ts), con credenciales
 * seed reales. El token queda en sessionStorage['auth-session'].
 *
 * Por qué se reescribió (T064): la versión anterior aseveraba un árbol que ya
 * no existe. Las lápidas «410» (`GonePage`, `gone-page`) se retiraron y esas
 * rutas hoy REDIRIGEN; el hub `/competitions/insights` (`hub-card-season`,
 * `hub-card-club`), `/competitions/insights/club` (`club-insights-*`), el
 * envoltorio `insights-tab-module` y el enlace «Análisis IA carreras» del menú
 * dejaron de existir (feature 029), y la 045 unificó el área bajo tres ítems:
 * «Competencias» · «Temporada» · «Cargas e identidades».
 *
 *   `/coach/race-analysis`                       → `/competitions`
 *   `/training/races/:id/club-insights`          → `/competitions/:id?tab=insights`
 *   `/competitions/insights`                     → 404 (lápida, NotFoundPage)
 *   `/competitions/insights/season/:year`        → `/competitions/season/:year`
 *   `/competitions/history`                      → `/competitions/imports?seccion=cargas`
 *   `/competitions/identity-review`              → `/competitions/imports?seccion=identidades`
 *   `/competitions/unlinked`                     → `/competitions/imports?seccion=sin-enlazar`
 *   `/competitions/:id?tab=conditions`           → `?tab=circuito` («Circuito y condiciones»)
 *   `/athletes/:id?tab=ai_analysis`              → `?tab=races&view=analisis`
 *
 * Privacidad: NO se hardcodean nombres de menores. Los asserts son
 * estructurales (data-testid, headings, roles) o sobre agregados.
 *
 * Cobertura: 10 escenarios cubribles con el seed actual (los redirects de la
 * 045 son una tabla, un test por ruta) + 2 skips documentados (PR4 diff
 * dropdown, PR5 análisis desactualizado) cuyo prerequisito de datos no existe
 * en el seed. NO se ejecutó en la sesión que lo escribió (carril diferido
 * T070: requiere el stack e2e aislado).
 */
import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Credenciales seed reales (entorno dev/Docker — NUNCA producción)
// ---------------------------------------------------------------------------

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const PARENT = { email: "padre@trochayruta.com", password: "Parent2026!" };

// Datos seed (deep-links). race_event id 5 = Válida IV Cali (completed, copa),
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
// Redirects de rutas retiradas (antes GonePage/410; hoy `<Navigate replace>`)
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — rutas retiradas redirigen", () => {
  test("E2E-CU-001: /coach/race-analysis redirige a /competitions", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/coach/race-analysis");

    // El hub IA se eliminó en la 029: el redirect aterriza en la lista.
    await expect(page).toHaveURL(/\/competitions$/, { timeout: NAV_TIMEOUT });
    await expect(
      page.getByRole("heading", { name: "Competencias", exact: true }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    // Ya no existe ninguna «Esta sección se movió» (GonePage).
    await expect(page.getByTestId("gone-page")).toHaveCount(0);
  });

  test("E2E-CU-002: /training/races/:id/club-insights redirige a /competitions/:id?tab=insights", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/training/races/${COMPLETED_RACE_ID}/club-insights`);

    await expect(page).toHaveURL(
      new RegExp(`/competitions/${COMPLETED_RACE_ID}\\?tab=insights$`),
      { timeout: NAV_TIMEOUT },
    );
    await expect(page.getByTestId("competition-tabs")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });
    await expect(page.getByTestId("gone-page")).toHaveCount(0);
  });

  test("E2E-CU-003: /competitions/insights (hub retirado) es una lápida 404, no una competencia inválida", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/insights");

    // Ruta estática explícita: sin ella React Router la resolvería como
    // `/competitions/:id` con id="insights" y mostraría el guard de id inválido.
    await expect(page.getByRole("heading", { name: "404" })).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });
    await expect(page.getByText("Ruta no encontrada.")).toBeVisible();
    await expect(page).toHaveURL(/\/competitions\/insights$/);
    // Ni el hub viejo ni sus accesos.
    await expect(page.getByTestId("hub-card-season")).toHaveCount(0);
    await expect(page.getByTestId("hub-card-club")).toHaveCount(0);
  });

  // Tres rutas de la 045 que pasaron a ser secciones de «Cargas e identidades».
  const IMPORTS_REDIRECTS = [
    { id: "005a", from: "/competitions/history", seccion: "cargas" },
    { id: "005b", from: "/competitions/identity-review", seccion: "identidades" },
    { id: "005c", from: "/competitions/unlinked", seccion: "sin-enlazar" },
  ] as const;

  for (const { id, from, seccion } of IMPORTS_REDIRECTS) {
    test(`E2E-CU-${id}: ${from} redirige a /competitions/imports?seccion=${seccion}`, async ({
      page,
    }) => {
      await loginAsCoach(page);

      await page.goto(from);

      await expect(page).toHaveURL(
        new RegExp(`/competitions/imports\\?seccion=${seccion}$`),
        { timeout: NAV_TIMEOUT },
      );
      await expect(
        page.getByRole("heading", { name: "Cargas e identidades" }),
      ).toBeVisible({ timeout: COLD_START_TIMEOUT });
      // La pestaña de la sección destino queda activa.
      await expect(page.getByTestId(`seccion-${seccion}`)).toHaveAttribute(
        "data-state",
        "active",
        { timeout: NAV_TIMEOUT },
      );
    });
  }

  test("E2E-CU-005d: /competitions/insights/season/:year redirige a /competitions/season/:year y conserva ?analisis=", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(
      `/competitions/insights/season/${SEASON_YEAR}?analisis=desactualizados`,
    );

    await expect(page).toHaveURL(
      new RegExp(
        `/competitions/season/${SEASON_YEAR}\\?analisis=desactualizados$`,
      ),
      { timeout: NAV_TIMEOUT },
    );
    // El panel «Análisis pendientes» abre en el modo pedido por el enlace.
    await expect(page.getByTestId("pending-analyses-panel")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });
    await expect(page.getByTestId("pending-mode-desactualizados")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });
});

// ---------------------------------------------------------------------------
// «Temporada» — panorama agregado (datos reales del backend)
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — Temporada", () => {
  test("E2E-CU-004: coach abre /competitions/season/:year y la tabla carga datos reales", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/competitions/season/${SEASON_YEAR}`);

    // Header de la página («Temporada 2026»; antes «Panorama de temporada»).
    await expect(
      page.getByRole("heading", { name: `Temporada ${SEASON_YEAR}` }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // Pastillas del área: «Competencias» · «Temporada» · «Cargas e identidades».
    const areaTabs = page.getByRole("tablist").first();
    await expect(areaTabs.getByRole("tab", { name: "Competencias", exact: true })).toBeVisible();
    await expect(areaTabs.getByRole("tab", { name: "Temporada", exact: true })).toBeVisible();
    await expect(
      areaTabs.getByRole("tab", { name: /^Cargas e identidades/ }),
    ).toBeVisible();

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

    // El panel de análisis pendientes vive sobre la tabla y arranca cerrado.
    await expect(page.getByTestId("open-pending-analyses")).toBeVisible();
    await expect(page.getByTestId("pending-analyses-panel")).toHaveCount(0);
  });

  test("E2E-CU-013: una fila de Temporada abre «Carreras › Análisis IA» del atleta y el alias ?tab=ai_analysis converge ahí", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/competitions/season/${SEASON_YEAR}`);
    const firstRow = page.locator('[data-testid^="season-row-"]').first();
    await expect(firstRow).toBeVisible({ timeout: COLD_START_TIMEOUT });
    const rowTestId = await firstRow.getAttribute("data-testid");
    const athleteId = rowTestId?.replace("season-row-", "");
    expect(athleteId).toMatch(/^\d+$/);

    await firstRow.click();

    // Enlace profundo canónico: una sola pestaña «Carreras», vista «Análisis IA».
    await expect(page).toHaveURL(
      new RegExp(`/athletes/${athleteId}\\?tab=races&view=analisis$`),
      { timeout: NAV_TIMEOUT },
    );
    await expect(page.getByTestId("athlete-tab-races")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });
    await expect(page.getByTestId("carreras-tab")).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("carreras-view-analisis")).toHaveAttribute(
      "data-state",
      "active",
    );
    await expect(page.getByTestId("analysis-view")).toBeVisible({ timeout: NAV_TIMEOUT });
    // La pestaña vieja «Insights IA» ya no existe.
    await expect(page.getByTestId("athlete-tab-ai-analysis")).toHaveCount(0);

    // Alias legado (correos ya enviados, marcadores): converge a la URL canónica.
    await page.goto(`/athletes/${athleteId}?tab=ai_analysis`);
    await expect(page).toHaveURL(
      new RegExp(`/athletes/${athleteId}\\?tab=races&view=analisis$`),
      { timeout: NAV_TIMEOUT },
    );
    await expect(page.getByTestId("analysis-view")).toBeVisible({ timeout: NAV_TIMEOUT });
  });
});

// ---------------------------------------------------------------------------
// «Cargas e identidades» — tres secciones bajo una sola ruta
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — Cargas e identidades", () => {
  test("E2E-CU-014: /competitions/imports abre en «Cargas» y alterna las tres secciones vía ?seccion=", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/imports");

    await expect(
      page.getByRole("heading", { name: "Cargas e identidades" }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // Sin ?seccion= (o con un valor desconocido) cae en «Cargas», nunca un error.
    await expect(page.getByTestId("seccion-cargas")).toHaveAttribute(
      "data-state",
      "active",
      { timeout: NAV_TIMEOUT },
    );

    await page.getByTestId("seccion-identidades").click();
    await expect(page).toHaveURL(/seccion=identidades/, { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("seccion-identidades")).toHaveAttribute(
      "data-state",
      "active",
    );

    await page.getByTestId("seccion-sin-enlazar").click();
    await expect(page).toHaveURL(/seccion=sin-enlazar/, { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("seccion-sin-enlazar")).toHaveAttribute(
      "data-state",
      "active",
    );
  });
});

// ---------------------------------------------------------------------------
// Detalle de la competencia — «Circuito y condiciones» y «Análisis IA»
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — pestañas del detalle", () => {
  test("E2E-CU-006: /competitions/:id?tab=insights monta el grid de «Análisis IA» scopeado a la válida", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/competitions/${COMPLETED_RACE_ID}?tab=insights`);

    // El detalle carga (el título es el <h1> del PageHeader; el gate estable
    // es el contenedor de pestañas).
    await expect(page.getByTestId("competition-tabs")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // Pestañas del contrato de copy: «Insights IA» se renombró «Análisis IA»,
    // «Condiciones» se fundió en «Circuito y condiciones», y «Clasificación»
    // aparece porque la válida 5 es de copa.
    const tablist = page.getByTestId("competition-tabs").getByRole("tablist");
    await expect(tablist.getByRole("tab", { name: "Análisis IA" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    await expect(
      tablist.getByRole("tab", { name: "Circuito y condiciones" }),
    ).toBeVisible();
    await expect(tablist.getByRole("tab", { name: "Clasificación" })).toBeVisible();
    await expect(tablist.getByRole("tab", { name: "Insights IA" })).toHaveCount(0);
    await expect(tablist.getByRole("tab", { name: "Condiciones", exact: true })).toHaveCount(0);

    // El tab SIEMPRE renderiza el grid scopeado a la válida (data-testid="insights-tab").
    await expect(page.getByTestId("insights-tab")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

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

  test("E2E-CU-015: ?tab=conditions es un alias de ?tab=circuito («Circuito y condiciones»)", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/competitions/${COMPLETED_RACE_ID}?tab=conditions`);

    // El alias se reescribe en la URL (contrato R-12) y la pestaña queda activa.
    await expect(page).toHaveURL(
      new RegExp(`/competitions/${COMPLETED_RACE_ID}\\?tab=circuito$`),
      { timeout: COLD_START_TIMEOUT },
    );
    await expect(
      page
        .getByTestId("competition-tabs")
        .getByRole("tab", { name: "Circuito y condiciones" }),
    ).toHaveAttribute("aria-selected", "true", { timeout: NAV_TIMEOUT });
  });
});

// ---------------------------------------------------------------------------
// RBAC — parent NO accede al área Competencias (parents → redirect)
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — RBAC parent", () => {
  test("E2E-CU-007: parent en /competitions/imports y /competitions/season/:year es redirigido a /my-athletes", async ({
    page,
  }) => {
    await loginAsParent(page);

    // ProtectedRoute(coach/admin) → parent cae a su landing /my-athletes.
    await page.goto("/competitions/imports");
    await expect(page).toHaveURL(/\/my-athletes$/, { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("seccion-identidades")).toHaveCount(0);

    await page.goto(`/competitions/season/${SEASON_YEAR}`);
    await expect(page).toHaveURL(/\/my-athletes$/, { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("season-insights-table")).toHaveCount(0);
  });

  test("E2E-CU-008: parent en las rutas legadas /competitions/insights/season/:year y /competitions/history cae en /my-athletes", async ({
    page,
  }) => {
    await loginAsParent(page);

    // La ruta vieja redirige a la nueva (sin guard) y la nueva sí lo tiene:
    // el redirect nunca abre una puerta que el guard mantiene cerrada.
    await page.goto(`/competitions/insights/season/${SEASON_YEAR}`);
    await expect(page).toHaveURL(/\/my-athletes$/, { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("season-insights-table")).toHaveCount(0);

    await page.goto("/competitions/history");
    await expect(page).toHaveURL(/\/my-athletes$/, { timeout: NAV_TIMEOUT });
    await expect(page.getByTestId("seccion-cargas")).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// PR6 — Checkbox "Crear evento en calendario" (D1: ON por default)
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — checkbox calendario", () => {
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
// Menú — un área «Competencias» con tres ítems, sin destinos legados
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — menú del área", () => {
  test("E2E-CU-010: el menú del coach agrupa Competencias · Temporada · Cargas e identidades, sin «Análisis IA carreras» ni rutas legadas", async ({
    page,
  }) => {
    await loginAsCoach(page);

    // En cualquier ruta de `/competitions*` el área está activa y su
    // disclosure se auto-expande, así los tres sub-ítems son links visibles.
    await page.goto("/competitions");
    const nav = page.getByRole("navigation", { name: "Secciones" }).first();
    await expect(nav).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // «Competencias» → /competitions (fila del área y primer sub-ítem).
    await expect(nav.locator('a[href="/competitions"]').first()).toBeVisible();

    // «Temporada» → `/competitions/season/<año vigente>`.
    const seasonLink = nav.locator('a[href^="/competitions/season/"]');
    await expect(seasonLink).toBeVisible();
    await expect(seasonLink).toHaveText(/^Temporada$/);
    await expect(seasonLink).toHaveAttribute("href", /^\/competitions\/season\/\d{4}$/);

    // «Cargas e identidades» → /competitions/imports (con insignia de pendientes
    // opcional en su nombre accesible: «Cargas e identidades · N pendientes»).
    const importsLink = nav.locator('a[href="/competitions/imports"]');
    await expect(importsLink).toBeVisible();
    await expect(importsLink).toContainText("Cargas e identidades");

    // Vocabulario retirado: ni «Válidas», ni «Sin enlazar», ni «Análisis IA carreras».
    await expect(nav.getByRole("link", { name: "Válidas" })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: /^Sin enlazar/ })).toHaveCount(0);
    await expect(nav.getByRole("link", { name: /análisis ia carreras/i })).toHaveCount(0);

    // NO debe existir NINGÚN link a rutas legadas.
    for (const legacy of [
      "/coach/race-analysis",
      "/competitions/insights",
      "/competitions/history",
      "/competitions/identity-review",
      "/competitions/unlinked",
    ]) {
      await expect(page.locator(`a[href="${legacy}"]`)).toHaveCount(0);
    }

    // Click en «Temporada» aterriza en la página, con la pastilla activa.
    await seasonLink.click();
    await expect(page).toHaveURL(/\/competitions\/season\/\d{4}$/, {
      timeout: NAV_TIMEOUT,
    });
    await expect(page.getByRole("heading", { name: /^Temporada \d{4}$/ })).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
  });
});

// ---------------------------------------------------------------------------
// PR4 / PR5 — requieren estado que el seed actual NO provee. Skips documentados.
// ---------------------------------------------------------------------------

test.describe("Competencias 045 — PR4/PR5 (prerequisitos de datos)", () => {
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

  // PR5 (reubicado por la 045): el aviso "desactualizado" ya no es el badge
  // `stale-analysis-badge` dentro del perfil del deportista (el componente
  // `StaleAnalysisBadge` quedó sin montar). Hoy vive en «Temporada» →
  // «Análisis pendientes» → «Desactualizados»
  // (`/competitions/season/:year?analisis=desactualizados`), una fila por run
  // con `stale_since != null`, con «Abrir análisis», «Re-ejecutar» y
  // «Descartar aviso». El seed tiene 48 agent_runs pero ninguno está marcado
  // stale (no hubo re-ingesta que invalide un run), así que la lista real sale
  // vacía y no se puede aseverar una fila. Forzarlo requeriría: (1) un run
  // aprobado para un atleta, (2) una re-ingesta que dispare
  // POST /runs/{id}/invalidate y poble stale_since. El flujo con datos se
  // cubre mockeado en `dashboard-coach.spec.ts` (destino de la fila «Insights
  // IA desactualizados») y en vitest (PendingAnalysesPanel).
  test.skip("E2E-CU-012: PR5 fila 'desactualizado' en Temporada › Análisis pendientes + re-ejecutar [prereq: run con stale_since != null]", async () => {
    // Prerequisito no disponible en el seed: agent_run con stale_since
    // poblado (requiere re-ingesta previa que invalide el run).
  });
});
