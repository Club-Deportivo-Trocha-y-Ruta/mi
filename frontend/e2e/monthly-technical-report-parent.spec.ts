/**
 * E2E del módulo Informe Técnico Mensual — vista del PADRE/MADRE (privacidad).
 *
 * Backend mockeado vía page.route (sin backend real ni red). Valida la invariante
 * de privacidad del refactor: el Informe Técnico Mensual es un documento INTERNO
 * del equipo técnico del club (coach/admin). Un padre NO accede a la ruta del
 * informe:
 * - La ruta /training/reports/:year/:month está protegida con allowedRoles
 *   [coach, admin] y el link del sidebar no se muestra a padres.
 * - Un padre que intente entrar por URL directa es redirigido a /my-athletes.
 * - En consecuencia no ve métricas, ni editores, ni botón de aprobar, ni descarga
 *   de PDF, ni tabla de competencia.
 *
 * (El componente ReportDetailPage conserva un ParentReadOnlyView defensivo, pero
 * no es alcanzable por routing/nav: ver e2e.md para la nota de código muerto.)
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const PARENT_USER = {
  id: 20,
  first_name: "Madre",
  last_name: "Ficticia",
  email: "madre@test.com",
  phone: null,
  role: "parent",
  is_active: true,
  can_login: true,
  club_ids: [1],
  created_at: "2026-01-01T00:00:00Z",
};

const FAKE_TOKENS = {
  access_token: "fake-access-token",
  refresh_token: "fake-refresh-token",
  token_type: "bearer",
};

const CLUB_ID = 1;
const YEAR = 2026;
const MONTH = 5;

// ---------------------------------------------------------------------------
// Fixture — vista del padre: narrative_blocks y competition_results llegan null
// ---------------------------------------------------------------------------

const PARENT_METRICS_SNAPSHOT = {
  total_sessions_executed: 8,
  total_sessions_cancelled: 1,
  total_minutes_executed: 0,
  avg_hours_per_week: null,
  avg_rubric_effort: 3.8,
  avg_rubric_attitude: 4.1,
  avg_rubric_technique: 3.5,
  technical_focus_counts: {},
  technical_focus_list: [],
  attendance_status_totals: {
    presente: 6,
    tarde: 1,
    justificado: 0,
    ausente: 1,
    lesionado: 0,
  },
  // Solo sus atletas (el backend ya filtra; sin athlete_names → "Atleta N").
  attendance_by_athlete: {
    "101": {
      count_present: 6,
      count_late: 1,
      count_justified: 0,
      count_absent: 1,
      count_injured: 0,
      total_sessions: 8,
      attendance_pct: 87.5,
    },
  },
};

const PARENT_REPORT_FIXTURE = {
  id: 1,
  club_id: CLUB_ID,
  year: YEAR,
  month: MONTH,
  ai_summary: null,
  metrics_snapshot: PARENT_METRICS_SNAPSHOT,
  coach_observations: null,
  // El backend NO envía nombres al padre en este fixture (cae a "Atleta N").
  athlete_names: null,
  status: "approved",
  // Contrato de privacidad: estos llegan null para el padre.
  narrative_blocks: null,
  competition_results: null,
  generated_at: "2026-05-31T12:00:00Z",
  generated_by_user_id: 10,
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function setupAuthParent(page: Page) {
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
    { tokens: FAKE_TOKENS, user: PARENT_USER },
  );
}

async function mockBackendForParent(page: Page) {
  // POST /api/auth/login → tokens fake
  await page.route("**/api/auth/login", (route: Route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(FAKE_TOKENS),
      });
    }
    return route.continue();
  });

  // GET /api/auth/me → parent user
  await page.route("**/api/auth/me", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(PARENT_USER),
    }),
  );

  // GET detalle del reporte → fixture del padre (blocks/results null).
  await page.route(
    "**/api/clubs/*/monthly-reports/*/*",
    async (route: Route) => {
      if (route.request().method() !== "GET") return route.continue();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(PARENT_REPORT_FIXTURE),
      });
    },
  );

  // Lista de reportes (por si el padre navega a /training/reports).
  await page.route("**/api/clubs/*/monthly-reports", async (route: Route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([PARENT_REPORT_FIXTURE]),
    });
  });

  // Periférico.
  await page.route("**/api/parent-athletes/my-athletes", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

const REPORT_PATH = `/training/reports/${YEAR}/${MONTH}`;

test.describe("Informe Técnico Mensual — parent E2E (privacidad)", () => {
  test("ITR-008: el padre NO accede al informe técnico (ruta coach) y es redirigido a /my-athletes", async ({
    page,
  }) => {
    // El mock es defensivo: cubre cualquier prefetch del SPA antes de que el
    // guard de ruta resuelva la redirección. El padre nunca debería llegar a
    // consumir el detalle del informe.
    await mockBackendForParent(page);
    await setupAuthParent(page);

    // El Informe Técnico Mensual es un documento interno del equipo técnico del
    // club. La ruta /training/reports/:year/:month está protegida con
    // allowedRoles [coach, admin]; el link del sidebar tampoco se muestra a
    // padres. Un padre autenticado que intente entrar por URL directa es
    // redirigido a su propia área (/my-athletes) por ProtectedRoute.
    await page.goto(REPORT_PATH);

    // Invariante de privacidad: es expulsado de la ruta del informe.
    await expect(page).toHaveURL(/\/my-athletes\/?$/, { timeout: 10_000 });

    // No ve NADA del informe técnico: ni tabla de métricas, ni editores de
    // bloque, ni botones de aprobar/descargar PDF, ni tabla de competición.
    await expect(page.getByTestId("monthly-metrics-table")).toHaveCount(0);
    await expect(page.locator('[data-testid^="block-editor-"]')).toHaveCount(0);
    await expect(page.getByTestId("approve-btn")).toHaveCount(0);
    await expect(page.getByTestId("download-pdf-button")).toHaveCount(0);
    await expect(page.getByTestId("competition-results-table")).toHaveCount(0);
    await expect(page.getByRole("button", { name: /aprobar/i })).toHaveCount(0);
  });
});
