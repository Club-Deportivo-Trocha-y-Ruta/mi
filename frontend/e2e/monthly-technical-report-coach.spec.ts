/**
 * E2E del módulo Informe Técnico Mensual (refactor del reporte mensual del club)
 * — vista del COACH.
 *
 * Backend mockeado vía page.route (no requiere backend real ni red). Valida el
 * wiring de rutas + frontend + contratos de API del módulo:
 * - Login coach (sesión inyectada en sessionStorage) y acceso a /training/reports
 * - Lista: badge de estado (Borrador/Aprobado) + enlace "Datos del proyecto"
 * - Detalle: 7 editores de bloque (en orden), tabla de métricas, tabla de competición
 * - Editar final_text de un bloque + Guardar → PATCH .../blocks (body + contador)
 * - Regenerar un bloque → POST .../regenerate (contador + ai_draft cambia)
 * - Aprobar → PATCH status=approved → badge "Aprobado" + editores deshabilitados
 * - Descargar PDF → GET .../pdf devuelve blob application/pdf (mock)
 * - Project profile: navegar, llenar, agregar/quitar objetivo, Guardar → PUT
 *
 * Los unit tests (vitest) cubren contratos y RBAC en detalle; este E2E valida el
 * flujo de UI end-to-end con mocks deterministas.
 *
 * NOTA DE ENTORNO: en el contenedor sin red NO se puede descargar Chromium ni
 * levantar el backend; estos specs se validaron con `playwright test --list`
 * (compilan/colectan). La ejecución con navegador queda para un entorno con red
 * (`npx playwright install chromium`). Ver docs/11-informe-tecnico-mensual/e2e.md.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Constantes
// ---------------------------------------------------------------------------

const COACH_USER = {
  id: 10,
  first_name: "Entrenador",
  last_name: "Test",
  email: "entrenador@test.com",
  phone: null,
  role: "coach",
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
const MONTH = 5; // Mayo

// Claves de bloque EN ORDEN (debe coincidir con BLOCK_ORDER de ReportDetailPage).
const BLOCK_KEYS = [
  "objetivo",
  "desarrollo",
  "resultados",
  "conclusiones",
  "apoyos_materiales",
  "analisis_grupo",
  "competencia",
] as const;

type BlockKey = (typeof BLOCK_KEYS)[number];

// ---------------------------------------------------------------------------
// Fixtures — sin nombres reales de menores (inventados ficticios)
// ---------------------------------------------------------------------------

function makeNarrativeBlocks(): Record<
  BlockKey,
  { ai_draft: string | null; final_text: string | null; ai_model: string | null; ai_generated_at: string | null }
> {
  const blocks = {} as Record<
    BlockKey,
    { ai_draft: string | null; final_text: string | null; ai_model: string | null; ai_generated_at: string | null }
  >;
  for (const key of BLOCK_KEYS) {
    blocks[key] = {
      ai_draft: `Borrador IA del bloque ${key}.`,
      final_text: `Texto final del bloque ${key}.`,
      ai_model: "gemini-2.5-flash-lite",
      ai_generated_at: "2026-05-31T10:00:00Z",
    };
  }
  return blocks;
}

const METRICS_SNAPSHOT = {
  total_sessions_executed: 8,
  total_sessions_cancelled: 1,
  total_minutes_executed: 720,
  avg_hours_per_week: 3.0,
  avg_rubric_effort: 3.8,
  avg_rubric_attitude: 4.1,
  avg_rubric_technique: 3.5,
  technical_focus_counts: { Frenada: 4, Curvas: 3 },
  technical_focus_list: ["Frenada", "Curvas"],
  attendance_status_totals: {
    presente: 30,
    tarde: 2,
    justificado: 1,
    ausente: 3,
    lesionado: 0,
  },
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
    "102": {
      count_present: 7,
      count_late: 0,
      count_justified: 1,
      count_absent: 0,
      count_injured: 0,
      total_sessions: 8,
      attendance_pct: 100.0,
    },
  },
};

const COMPETITION_RESULTS = [
  {
    athlete_name: "Valentina Garcia",
    category: "Pre-Infantil",
    position: 3,
    points: 16,
    event_name: "Copa Valle Válida IV — Cali",
    event_date: "2026-05-17",
  },
  {
    athlete_name: "Mateo Lopez",
    category: "Pre-Infantil",
    position: 5,
    points: 11,
    event_name: "Copa Valle Válida IV — Cali",
    event_date: "2026-05-17",
  },
];

function makeReportFixture(
  overrides?: Partial<Record<string, unknown>>,
): Record<string, unknown> {
  return {
    id: 1,
    club_id: CLUB_ID,
    year: YEAR,
    month: MONTH,
    ai_summary: "Resumen del mes de mayo del club.",
    metrics_snapshot: METRICS_SNAPSHOT,
    coach_observations: "Observaciones del entrenador para el período.",
    athlete_names: {
      "101": "Valentina Garcia",
      "102": "Mateo Lopez",
    },
    status: "draft",
    narrative_blocks: makeNarrativeBlocks(),
    competition_results: COMPETITION_RESULTS,
    generated_at: "2026-05-31T12:00:00Z",
    generated_by_user_id: COACH_USER.id,
    ...overrides,
  };
}

const PROJECT_PROFILE_FIXTURE = {
  id: 1,
  club_id: CLUB_ID,
  project_name: "Formación deportiva XCO Valle del Cauca",
  executing_entity: "Club Deportivo Trocha y Ruta",
  report_responsible: "Coordinador Ficticio",
  purpose: "Promover el ciclismo de montaña juvenil.",
  general_objective: "Desarrollar habilidades técnicas y disfrute del deporte.",
  specific_objectives: ["Mejorar técnica de descenso", "Fomentar el multideporte"],
  territory_location: "Cali, Valle del Cauca",
  territory_description: "Zona de media montaña apta para XCO.",
};

// ---------------------------------------------------------------------------
// Helpers de setup
// ---------------------------------------------------------------------------

async function setupAuth(page: Page) {
  // Inyecta sesión autenticada en sessionStorage (formato del Zustand store).
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
    { tokens: FAKE_TOKENS, user: COACH_USER },
  );
}

interface MockState {
  /** Reporte detallado actual (mutable: aprobar/patch/regenerar lo modifican). */
  currentReport: Record<string, unknown>;
  patchCalls: number;
  patchBodies: unknown[];
  regenerateCalls: number;
  regeneratedKeys: string[];
  pdfCalls: number;
  putCalls: number;
  putBodies: unknown[];
}

async function mockBackendForCoach(page: Page): Promise<MockState> {
  const state: MockState = {
    currentReport: makeReportFixture(),
    patchCalls: 0,
    patchBodies: [],
    regenerateCalls: 0,
    regeneratedKeys: [],
    pdfCalls: 0,
    putCalls: 0,
    putBodies: [],
  };

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

  // GET /api/auth/me → coach user
  await page.route("**/api/auth/me", (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(COACH_USER),
    }),
  );

  // --- PROJECT PROFILE: GET/PUT/PATCH ---
  // Debe ir ANTES del handler genérico de monthly-reports (no colisiona, pero
  // mantenemos el orden por claridad).
  await page.route(
    "**/api/clubs/*/project-profile",
    async (route: Route) => {
      const method = route.request().method();
      if (method === "GET") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(PROJECT_PROFILE_FIXTURE),
        });
      }
      if (method === "PUT" || method === "PATCH") {
        state.putCalls += 1;
        const body = route.request().postDataJSON();
        state.putBodies.push(body);
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ...PROJECT_PROFILE_FIXTURE, ...body }),
        });
      }
      return route.continue();
    },
  );

  // --- PDF: GET .../monthly-reports/{y}/{m}/pdf → blob application/pdf ---
  await page.route(
    "**/api/clubs/*/monthly-reports/*/*/pdf",
    async (route: Route) => {
      if (route.request().method() !== "GET") return route.continue();
      state.pdfCalls += 1;
      // Cuerpo mínimo de PDF válido (header %PDF-).
      const pdfBytes = Buffer.from("%PDF-1.4\n%mock-pdf\n%%EOF\n", "utf-8");
      return route.fulfill({
        status: 200,
        contentType: "application/pdf",
        body: pdfBytes,
      });
    },
  );

  // --- REGENERAR bloque: POST .../blocks/{key}/regenerate ---
  await page.route(
    "**/api/clubs/*/monthly-reports/*/*/blocks/*/regenerate",
    async (route: Route) => {
      if (route.request().method() !== "POST") return route.continue();
      state.regenerateCalls += 1;
      const match = route
        .request()
        .url()
        .match(/\/blocks\/([^/]+)\/regenerate/);
      const blockKey = (match?.[1] ?? "objetivo") as BlockKey;
      state.regeneratedKeys.push(blockKey);

      // Muta el bloque: nuevo ai_draft que DIFIERE del final_text actual.
      const blocks = {
        ...(state.currentReport.narrative_blocks as Record<BlockKey, unknown>),
      };
      blocks[blockKey] = {
        ai_draft: `Borrador IA REGENERADO del bloque ${blockKey}.`,
        final_text: null,
        ai_model: "gemini-2.5-flash-lite",
        ai_generated_at: new Date().toISOString(),
      };
      state.currentReport = {
        ...state.currentReport,
        narrative_blocks: blocks,
      };
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.currentReport),
      });
    },
  );

  // --- PATCH .../blocks → editar bloques o cambiar status ---
  await page.route(
    "**/api/clubs/*/monthly-reports/*/*/blocks",
    async (route: Route) => {
      if (route.request().method() !== "PATCH") return route.continue();
      state.patchCalls += 1;
      const body = route.request().postDataJSON() as {
        blocks?: Record<string, string>;
        status?: "draft" | "approved";
      };
      state.patchBodies.push(body);

      // Aplicar cambios al reporte mutable.
      if (body.status) {
        state.currentReport = { ...state.currentReport, status: body.status };
      }
      if (body.blocks) {
        const blocks = {
          ...(state.currentReport.narrative_blocks as Record<BlockKey, Record<string, unknown>>),
        };
        for (const [k, text] of Object.entries(body.blocks)) {
          blocks[k as BlockKey] = {
            ...(blocks[k as BlockKey] ?? {}),
            final_text: text,
          };
        }
        state.currentReport = { ...state.currentReport, narrative_blocks: blocks };
      }
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.currentReport),
      });
    },
  );

  // --- GET detalle .../monthly-reports/{y}/{m} ---
  await page.route(
    "**/api/clubs/*/monthly-reports/*/*",
    async (route: Route) => {
      const method = route.request().method();
      // Solo GET de detalle (los sub-paths /pdf, /blocks ya están capturados arriba).
      if (method !== "GET") return route.continue();
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(state.currentReport),
      });
    },
  );

  // --- GET lista + POST crear/regenerar .../monthly-reports ---
  await page.route(
    "**/api/clubs/*/monthly-reports",
    async (route: Route) => {
      const method = route.request().method();
      if (method === "GET") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([state.currentReport]),
        });
      }
      if (method === "POST") {
        return route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(state.currentReport),
        });
      }
      return route.continue();
    },
  );

  // Endpoints periféricos que el shell de la app puede disparar.
  await page.route("**/api/parent-athletes/my-athletes", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );

  return state;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

const REPORT_PATH = `/training/reports/${YEAR}/${MONTH}`;

test.describe("Informe Técnico Mensual — coach E2E", () => {
  test("ITR-001: lista muestra badge de estado y enlace 'Datos del proyecto'", async ({
    page,
  }) => {
    await mockBackendForCoach(page);
    await setupAuth(page);

    await page.goto("/training/reports");

    // Enlace a Datos del proyecto presente.
    const profileLink = page.getByTestId("project-profile-link");
    await expect(profileLink).toBeVisible({ timeout: 10_000 });
    await expect(profileLink).toHaveText(/datos del proyecto/i);

    // El badge de estado del reporte (Borrador) aparece en la lista. El fixture
    // se renderiza en card mobile y tabla desktop; el texto "Borrador" basta.
    await expect(page.getByText("Borrador").first()).toBeVisible();
  });

  test("ITR-002: detalle renderiza 7 editores en orden, métricas y competición", async ({
    page,
  }) => {
    await mockBackendForCoach(page);
    await setupAuth(page);

    await page.goto(REPORT_PATH);

    // Tabla de métricas.
    await expect(page.getByTestId("monthly-metrics-table")).toBeVisible({
      timeout: 10_000,
    });
    await expect(page.getByTestId("attendance-table")).toBeVisible();

    // Los 7 editores de bloque están presentes.
    for (const key of BLOCK_KEYS) {
      await expect(page.getByTestId(`block-editor-${key}`)).toBeVisible();
    }

    // Orden de los editores: el data-testid de cada uno debe aparecer en el DOM
    // en el mismo orden que BLOCK_KEYS.
    const editorTestIds = await page
      .locator('[data-testid^="block-editor-"]')
      .evaluateAll((els) => els.map((el) => el.getAttribute("data-testid")));
    expect(editorTestIds).toEqual(BLOCK_KEYS.map((k) => `block-editor-${k}`));

    // Tabla de competición con los resultados ficticios.
    await expect(page.getByTestId("competition-results-table")).toBeVisible();
    await expect(
      page.getByTestId("competition-results-table"),
    ).toContainText("Valentina Garcia");
  });

  test("ITR-003: editar final_text de un bloque y Guardar dispara PATCH .../blocks", async ({
    page,
  }) => {
    const state = await mockBackendForCoach(page);
    await setupAuth(page);

    await page.goto(REPORT_PATH);

    const editor = page.getByTestId("block-editor-objetivo");
    await expect(editor).toBeVisible({ timeout: 10_000 });

    const textarea = page.getByTestId("block-textarea-objetivo");
    const nuevoTexto =
      "Texto editado por el coach para el bloque objetivo del período.";
    await textarea.fill(nuevoTexto);

    await page.getByTestId("save-btn-objetivo").click();

    // El botón muestra feedback "Guardado" tras el PATCH exitoso.
    await expect(page.getByTestId("save-btn-objetivo")).toHaveText(/guardado/i, {
      timeout: 5_000,
    });

    // PATCH llamado exactamente una vez con el body esperado.
    expect(state.patchCalls).toBe(1);
    expect(state.patchBodies[0]).toMatchObject({
      blocks: { objetivo: nuevoTexto },
    });
  });

  test("ITR-004: regenerar un bloque dispara POST .../regenerate y cambia el ai_draft", async ({
    page,
  }) => {
    const state = await mockBackendForCoach(page);
    await setupAuth(page);

    await page.goto(REPORT_PATH);

    const editor = page.getByTestId("block-editor-desarrollo");
    await expect(editor).toBeVisible({ timeout: 10_000 });

    await page.getByTestId("regenerate-btn-desarrollo").click();

    // El textarea adopta el nuevo ai_draft devuelto por el mock.
    await expect(page.getByTestId("block-textarea-desarrollo")).toHaveValue(
      /REGENERADO/i,
      { timeout: 5_000 },
    );

    expect(state.regenerateCalls).toBe(1);
    expect(state.regeneratedKeys).toEqual(["desarrollo"]);
  });

  test("ITR-005: aprobar dispara PATCH status=approved, badge 'Aprobado' y editores deshabilitados", async ({
    page,
  }) => {
    const state = await mockBackendForCoach(page);
    await setupAuth(page);

    await page.goto(REPORT_PATH);

    await expect(page.getByTestId("approve-btn")).toBeVisible({ timeout: 10_000 });
    // Estado inicial: badge Borrador.
    await expect(page.getByTestId("status-badge-draft")).toBeVisible();

    await page.getByTestId("approve-btn").click();

    // Tras la mutation, el badge pasa a Aprobado.
    await expect(page.getByTestId("status-badge-approved")).toBeVisible({
      timeout: 5_000,
    });

    // PATCH con status=approved.
    expect(state.patchCalls).toBe(1);
    expect(state.patchBodies[0]).toMatchObject({ status: "approved" });

    // Editores deshabilitados: el textarea y los botones del primer bloque.
    await expect(page.getByTestId("block-textarea-objetivo")).toBeDisabled();
    await expect(page.getByTestId("save-btn-objetivo")).toBeDisabled();
    await expect(page.getByTestId("regenerate-btn-objetivo")).toBeDisabled();
    // El botón Aprobar también queda deshabilitado (ya está aprobado).
    await expect(page.getByTestId("approve-btn")).toBeDisabled();
  });

  test("ITR-006: descargar PDF llama GET .../pdf (blob application/pdf) sin romper la UI", async ({
    page,
  }) => {
    const state = await mockBackendForCoach(page);
    await setupAuth(page);

    await page.goto(REPORT_PATH);

    const downloadBtn = page.getByTestId("download-pdf-button");
    await expect(downloadBtn).toBeVisible({ timeout: 10_000 });

    // Esperamos la respuesta del endpoint PDF concurrente al click.
    const [pdfResponse] = await Promise.all([
      page.waitForResponse((resp) => /\/monthly-reports\/.*\/pdf$/.test(resp.url())),
      downloadBtn.click(),
    ]);

    expect(pdfResponse.status()).toBe(200);
    expect(pdfResponse.headers()["content-type"]).toContain("application/pdf");
    expect(state.pdfCalls).toBe(1);

    // No debe haber banner de error de descarga y el botón sigue presente.
    await expect(page.getByTestId("download-error-banner")).toHaveCount(0);
    await expect(downloadBtn).toBeVisible();
  });

  test("ITR-007: project profile — llenar, agregar/quitar objetivo y Guardar dispara PUT", async ({
    page,
  }) => {
    const state = await mockBackendForCoach(page);
    await setupAuth(page);

    await page.goto("/training/reports/project-profile");

    // El form carga con el perfil existente.
    await expect(page.getByLabel(/nombre del proyecto/i)).toBeVisible({
      timeout: 10_000,
    });

    // Editar un campo de texto.
    const nameInput = page.getByLabel(/nombre del proyecto/i);
    await nameInput.fill("Proyecto Editado E2E");

    // Agregar un objetivo específico nuevo. El fixture trae 2 → será el índice 2.
    await page.getByTestId("add-objective-btn").click();
    const nuevoObjetivo = page.getByLabel("Objetivo específico 3", { exact: true });
    await expect(nuevoObjetivo).toBeVisible();
    await nuevoObjetivo.fill("Objetivo específico añadido en E2E");

    // Quitar el primer objetivo (Eliminar objetivo 1).
    await page.getByRole("button", { name: /eliminar objetivo 1/i }).click();

    // Guardar.
    await page.getByTestId("save-profile-btn").click();

    // Mensaje de éxito tras el PUT.
    await expect(page.getByTestId("save-success-msg")).toBeVisible({
      timeout: 5_000,
    });

    // PUT llamado una vez con el nombre editado.
    expect(state.putCalls).toBe(1);
    expect(state.putBodies[0]).toMatchObject({
      project_name: "Proyecto Editado E2E",
    });
    // El payload de objetivos refleja el quitar+agregar (filtra vacíos en el page):
    // el primer objetivo original fue eliminado y se añadió uno nuevo.
    const body = state.putBodies[0] as { specific_objectives: string[] };
    expect(body.specific_objectives).toContain("Objetivo específico añadido en E2E");
    expect(body.specific_objectives).not.toContain("Mejorar técnica de descenso");
  });
});
