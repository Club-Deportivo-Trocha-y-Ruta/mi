/**
 * E2E del módulo Informe Técnico Mensual — vista del PADRE/MADRE (privacidad).
 *
 * Backend mockeado vía page.route (sin backend real ni red). Valida que la vista
 * de solo lectura del padre respeta el contrato de privacidad del refactor:
 * - El backend entrega narrative_blocks=null y competition_results=null al padre.
 * - La UI NO muestra editores de bloque, NO muestra el botón Aprobar, NO muestra
 *   el botón de descarga de PDF.
 * - SÍ muestra la nota "solo para el equipo técnico del club" y la tabla de
 *   métricas de asistencia.
 *
 * El informe técnico completo (PDF) es un documento interno del equipo técnico;
 * las familias no lo descargan.
 *
 * NOTA DE ENTORNO: en el contenedor sin red NO se puede descargar Chromium ni
 * levantar el backend; estos specs se validaron con `playwright test --list`
 * (compilan/colectan). La ejecución con navegador queda para un entorno con red.
 * Ver docs/11-informe-tecnico-mensual/e2e.md.
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
  test("ITR-008: el padre ve métricas y la nota, pero NO editores, NO aprobar, NO PDF", async ({
    page,
  }) => {
    await mockBackendForParent(page);
    await setupAuthParent(page);

    await page.goto(REPORT_PATH);

    // SÍ aparece la tabla de métricas.
    await expect(page.getByTestId("monthly-metrics-table")).toBeVisible({
      timeout: 10_000,
    });

    // SÍ aparece la nota de privacidad "solo para el equipo técnico del club".
    await expect(
      page.getByText(/solo para el equipo técnico del club/i),
    ).toBeVisible();

    // NO hay editores de bloque (ninguno de las 7 claves).
    await expect(page.locator('[data-testid^="block-editor-"]')).toHaveCount(0);

    // NO hay botón Aprobar.
    await expect(page.getByTestId("approve-btn")).toHaveCount(0);

    // NO hay botón de descarga de PDF.
    await expect(page.getByTestId("download-pdf-button")).toHaveCount(0);

    // NO hay tabla de competición (results=null → ni siquiera el contenedor coach).
    await expect(page.getByTestId("competition-results-table")).toHaveCount(0);

    // Invariante adicional: no aparece texto de "Aprobar" como botón en la vista
    // del padre.
    await expect(page.getByRole("button", { name: /aprobar/i })).toHaveCount(0);
  });
});
