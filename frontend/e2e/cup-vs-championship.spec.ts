/**
 * E2E spec 014 — Cup vs Championship Series
 *
 * Cubre los acceptance criteria de spec 014: discriminación copa/campeonato
 * en el formulario de competencias, el wizard de importación y el detalle.
 *
 * Stack real (no mocks):
 *   - Backend FastAPI en http://localhost:8000 con migración b1c2d3e4f5a6 aplicada.
 *   - Frontend Vite en http://localhost:5173 (reuseExistingServer).
 *
 * Seed relevante:
 *   - Serie id=2 "Copa Valle de Ciclomontañismo" (kind=cup, 4 válidas).
 *   - Serie id=4 "Campeonato Departamental 2026" (kind=championship).
 *   - race_event id=5 = Válida IV Cali (is_championship=false, completed).
 *
 * Privacidad: NUNCA se hardcodean nombres ni DOB de menores.
 * Los asserts son estructurales: data-testid, roles, headings, conteos.
 *
 * Bug detectado: raceSeries.ts usaba BASE sin trailing slash → 307 redirect
 * bypass del token Authorization → spinner infinito "Cargando series…".
 * Corregido en src/api/raceSeries.ts (GET BASE + "/", POST BASE + "/").
 */
import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Credenciales seed reales (entorno dev/Docker — NUNCA producción)
// ---------------------------------------------------------------------------

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const BACKEND = "http://localhost:8000";

// IDs del seed
const CUP_RACE_EVENT_ID = 5; // Válida IV Cali — is_championship=false, completed
const CHAMPIONSHIP_SERIES_ID = 4; // Campeonato Departamental 2026 — kind=championship

// Timeouts — tolerancia a cold-start del backend (primera query a MySQL)
const COLD_START_TIMEOUT = 90_000;
const NAV_TIMEOUT = 30_000;

// ---------------------------------------------------------------------------
// Helpers de login — mismo patrón que competitions-unification.spec.ts
// ---------------------------------------------------------------------------

async function login(
  page: Page,
  creds: { email: string; password: string },
): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(creds.email);
  await page
    .getByRole("textbox", { name: /contraseña/i })
    .fill(creds.password);
  await page.getByRole("button", { name: /ingresar/i }).click();

  // Esperar redirección fuera de /login tras auth exitosa
  await expect(page).not.toHaveURL(/\/login/, {
    timeout: COLD_START_TIMEOUT,
  });

  // Verificar token en sessionStorage
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

/**
 * Obtiene el token de acceso de sessionStorage.
 * Usado para hacer requests directos al backend desde el contexto del browser.
 */
async function getTokenFromSession(page: Page): Promise<string> {
  return page.evaluate(() => {
    const raw = sessionStorage.getItem("auth-session");
    if (!raw) return "";
    try {
      return JSON.parse(raw)?.state?.accessToken ?? "";
    } catch {
      return "";
    }
  });
}

// ---------------------------------------------------------------------------
// E2E-014-001: Form crear — Copa muestra "Número de válida" y lista Copa Valle
// ---------------------------------------------------------------------------

test.describe("spec 014 — Form crear: tipo Copa", () => {
  test("E2E-014-001: al seleccionar Copa, el campo 'Número de válida' es visible y el picker lista series de copa", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/new");

    // El formulario carga
    await expect(
      page.getByRole("heading", { name: /nueva competencia/i }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    // El selector de tipo existe y su valor por defecto es "cup"
    const kindSelect = page.locator("#competition-kind");
    await expect(kindSelect).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(kindSelect).toHaveValue("cup");

    // "Número de válida" visible para copa
    await expect(page.locator("#sequence-number")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // El picker de series carga (esperar que desaparezca el skeleton de carga)
    await expect(page.locator("text=Cargando series…")).toHaveCount(0, {
      timeout: NAV_TIMEOUT,
    });

    // El picker de series muestra un <select#series-id> con al menos la serie copa
    const seriesSelect = page.locator("#series-id");
    await expect(seriesSelect).toBeVisible({ timeout: NAV_TIMEOUT });

    // Hay al menos una opción distinta del placeholder (value=0)
    const optionCount = await seriesSelect.locator("option").count();
    expect(optionCount).toBeGreaterThan(1); // placeholder + al menos 1 serie copa
  });
});

// ---------------------------------------------------------------------------
// E2E-014-002: Form crear — Campeonato oculta "Número de válida" y lista
// series de campeonato (NO hardcodea Copa Valle)
// ---------------------------------------------------------------------------

test.describe("spec 014 — Form crear: tipo Campeonato", () => {
  test("E2E-014-002: al seleccionar Campeonato, se oculta 'Número de válida' y aparecen series de campeonato", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/new");

    await expect(
      page.getByRole("heading", { name: /nueva competencia/i }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    const kindSelect = page.locator("#competition-kind");
    await expect(kindSelect).toBeVisible({ timeout: NAV_TIMEOUT });

    // Cambiar a "Campeonato"
    await kindSelect.selectOption("championship");

    // "Número de válida" DESAPARECE para campeonato
    await expect(page.locator("#sequence-number")).toHaveCount(0, {
      timeout: NAV_TIMEOUT,
    });

    // El label "Número de válida" tampoco debe estar
    await expect(
      page.getByText(/número de válida/i, { exact: false }),
    ).toHaveCount(0);

    // El picker de series carga series de tipo campeonato
    await expect(page.locator("text=Cargando series…")).toHaveCount(0, {
      timeout: NAV_TIMEOUT,
    });

    // En el seed, hay 1 serie de campeonato (id=4), el select #series-id debe aparecer
    const seriesSelect = page.locator("#series-id");
    await expect(seriesSelect).toBeVisible({ timeout: NAV_TIMEOUT });

    // El valor inicial del picker debe ser el placeholder (value=0 = sin selección)
    await expect(seriesSelect).toHaveValue("0");

    // Las opciones disponibles deben incluir la serie de campeonato del seed
    const optionTexts = await seriesSelect
      .locator("option")
      .allTextContents();
    // Al menos una opción (además del placeholder) debe existir
    expect(optionTexts.length).toBeGreaterThan(1);

    // Ninguna opción debe ser "Copa Valle" (las series de copa no aparecen en el picker
    // cuando el tipo seleccionado es "championship")
    const hasCupsInChampList = optionTexts.some((t) =>
      t.toLowerCase().includes("copa valle"),
    );
    expect(hasCupsInChampList).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// E2E-014-003: Crear el ÚNICO evento del campeonato
// Idempotente: consulta la API para saber si ya existe; si hay 0 eventos
// crea uno y verifica el detalle; si ya hay 1 evento documenta como ya creado.
// ---------------------------------------------------------------------------

test.describe("spec 014 — Crear evento de campeonato", () => {
  test("E2E-014-003: crear el evento único de la serie Campeonato Departamental 2026 navega al detalle con badge CD", async ({
    page,
  }) => {
    await loginAsCoach(page);

    // Consultar cuántos eventos tiene la serie de campeonato (idempotencia)
    const token = await getTokenFromSession(page);
    const seriesDataStr = await page.evaluate(
      async ([url, tok]) => {
        try {
          const resp = await fetch(`${url}/api/race-analysis/race-series/`, {
            headers: { Authorization: `Bearer ${tok}` },
          });
          return JSON.stringify(await resp.json());
        } catch {
          return "{}";
        }
      },
      [BACKEND, token] as [string, string],
    );

    const seriesData = JSON.parse(seriesDataStr) as {
      items?: { id: number; kind: string; event_count: number }[];
    };
    const champSeries = (seriesData.items ?? []).find(
      (s) => s.id === CHAMPIONSHIP_SERIES_ID,
    );

    if (champSeries && champSeries.event_count > 0) {
      // El evento ya existe — verificar que el detalle muestra badge CD
      // Obtener el ID del evento de campeonato via API
      const eventsDataStr = await page.evaluate(
        async ([url, tok]) => {
          try {
            const resp = await fetch(
              `${url}/api/race-analysis/race-events/?include_championship=true`,
              { headers: { Authorization: `Bearer ${tok}` } },
            );
            return JSON.stringify(await resp.json());
          } catch {
            return "{}";
          }
        },
        [BACKEND, token] as [string, string],
      );

      const eventsData = JSON.parse(eventsDataStr) as {
        items?: { id: number; is_championship: boolean; series_id: number }[];
      };
      const champEvent = (eventsData.items ?? []).find(
        (e) => e.is_championship && e.series_id === CHAMPIONSHIP_SERIES_ID,
      );

      if (!champEvent) {
        test.skip(
          true,
          "No se encontró el evento de campeonato en la API — estado inesperado del DB",
        );
        return;
      }

      // Navegar al detalle del campeonato existente
      await page.goto(`/competitions/${champEvent.id}`);

      await expect(page.getByTestId("competition-title")).toBeVisible({
        timeout: NAV_TIMEOUT,
      });

      // Badge CD debe estar presente
      await expect(page.getByTestId("badge-championship")).toBeVisible({
        timeout: NAV_TIMEOUT,
      });

      // Tab Clasificación NO debe existir
      await expect(
        page.getByRole("tab", { name: /clasificación/i }),
      ).toHaveCount(0);

      // Test exitoso (evento preexistente verificado)
      return;
    }

    // Caso: la serie tiene 0 eventos → crear uno nuevo
    await page.goto("/competitions/new");

    await expect(
      page.getByRole("heading", { name: /nueva competencia/i }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    const kindSelect = page.locator("#competition-kind");
    await expect(kindSelect).toBeVisible({ timeout: NAV_TIMEOUT });
    await kindSelect.selectOption("championship");

    const seriesSelect = page.locator("#series-id");
    await expect(seriesSelect).toBeVisible({ timeout: NAV_TIMEOUT });

    const optionCount = await seriesSelect.locator("option").count();
    if (optionCount <= 1) {
      test.skip(
        true,
        "No hay series de campeonato en el picker — seed incompleto",
      );
      return;
    }

    // Seleccionar la primera serie de campeonato disponible (seed: id=4)
    const options = await seriesSelect.locator("option").all();
    let championshipSeriesValue = "";
    for (const opt of options) {
      const val = await opt.getAttribute("value");
      if (val && val !== "0") {
        championshipSeriesValue = val;
        break;
      }
    }

    if (!championshipSeriesValue) {
      test.skip(
        true,
        "No se encontró opción válida en el picker de series de campeonato",
      );
      return;
    }

    await seriesSelect.selectOption(championshipSeriesValue);

    // Verificar que "Número de válida" sigue oculto tras seleccionar serie
    await expect(page.locator("#sequence-number")).toHaveCount(0);

    // Rellenar nombre del evento (ficticio — no datos de menores)
    const nameInput = page.locator("#event-name");
    await expect(nameInput).toBeVisible();
    await nameInput.fill("Campeonato Departamental · Ginebra");

    // Rellenar fecha
    const dateInput = page.locator("#event-date");
    await expect(dateInput).toBeVisible();
    await dateInput.fill("2026-06-12");

    // Guardar
    const submitButton = page.getByRole("button", {
      name: /crear competencia/i,
    });
    await expect(submitButton).toBeVisible();
    await submitButton.click();

    // Creación exitosa → navega a /competitions/:newId
    await expect(page).toHaveURL(/\/competitions\/\d+$/, {
      timeout: NAV_TIMEOUT,
    });

    // El detalle muestra badge "CD" (is_championship=true)
    await expect(page.getByTestId("badge-championship")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // El título existe (structurally, sin asumir texto específico)
    await expect(page.getByTestId("competition-title")).toBeVisible();

    // El tab Clasificación NO existe para campeonatos
    await expect(
      page.getByRole("tab", { name: /clasificación/i }),
    ).toHaveCount(0, { timeout: NAV_TIMEOUT });
  });
});

// ---------------------------------------------------------------------------
// E2E-014-004: Guard single-event — intentar crear un SEGUNDO evento
// en la misma serie de campeonato muestra error 409
// Requiere que haya al menos 1 evento en la serie de campeonato (seed o
// E2E-014-003 lo habrá creado antes).
// ---------------------------------------------------------------------------

test.describe("spec 014 — Guard single-event campeonato", () => {
  test("E2E-014-004: intentar crear un segundo evento en la misma serie de campeonato muestra error del guard 409", async ({
    page,
  }) => {
    await loginAsCoach(page);

    // Verificar que la serie tiene al menos 1 evento (prerequisito del guard)
    const token = await getTokenFromSession(page);
    const seriesDataStr = await page.evaluate(
      async ([url, tok]) => {
        try {
          const resp = await fetch(`${url}/api/race-analysis/race-series/`, {
            headers: { Authorization: `Bearer ${tok}` },
          });
          return JSON.stringify(await resp.json());
        } catch {
          return "{}";
        }
      },
      [BACKEND, token] as [string, string],
    );

    const seriesData = JSON.parse(seriesDataStr) as {
      items?: { id: number; kind: string; event_count: number }[];
    };
    const champSeries = (seriesData.items ?? []).find(
      (s) => s.id === CHAMPIONSHIP_SERIES_ID,
    );

    if (!champSeries || champSeries.event_count === 0) {
      // No hay evento previo — crear uno primero para poder probar el guard
      // (el test de guard necesita que ya exista 1 evento)
      await page.goto("/competitions/new");
      await expect(
        page.getByRole("heading", { name: /nueva competencia/i }),
      ).toBeVisible({ timeout: COLD_START_TIMEOUT });

      await page.locator("#competition-kind").selectOption("championship");

      const seriesSelect = page.locator("#series-id");
      await expect(seriesSelect).toBeVisible({ timeout: NAV_TIMEOUT });

      const options = await seriesSelect.locator("option").all();
      let val = "";
      for (const opt of options) {
        const v = await opt.getAttribute("value");
        if (v && v !== "0") {
          val = v;
          break;
        }
      }
      if (!val) {
        test.skip(true, "No hay series de campeonato disponibles");
        return;
      }

      await seriesSelect.selectOption(val);
      await page.locator("#event-name").fill("Campeonato Departamental · Ginebra");
      await page.locator("#event-date").fill("2026-06-12");
      await page.getByRole("button", { name: /crear competencia/i }).click();

      // Esperar navegación al detalle (primer evento creado)
      await expect(page).toHaveURL(/\/competitions\/\d+$/, {
        timeout: NAV_TIMEOUT,
      });
    }

    // Ahora intentar crear un SEGUNDO evento en la misma serie de campeonato
    await page.goto("/competitions/new");

    await expect(
      page.getByRole("heading", { name: /nueva competencia/i }),
    ).toBeVisible({ timeout: COLD_START_TIMEOUT });

    await page.locator("#competition-kind").selectOption("championship");

    const seriesSelect = page.locator("#series-id");
    await expect(seriesSelect).toBeVisible({ timeout: NAV_TIMEOUT });

    // La serie ahora muestra "(1 evento)" en el texto de la opción
    const options = await seriesSelect.locator("option").all();
    let val = "";
    for (const opt of options) {
      const v = await opt.getAttribute("value");
      if (v && v !== "0") {
        val = v;
        break;
      }
    }

    if (!val) {
      test.skip(true, "No hay series de campeonato en el picker");
      return;
    }

    await seriesSelect.selectOption(val);

    await page.locator("#event-name").fill("Segundo evento CD (debe fallar)");
    await page.locator("#event-date").fill("2026-08-15");
    await page.getByRole("button", { name: /crear competencia/i }).click();

    // Esperar la respuesta del backend (el guard 409 debería aparecer)
    // El formulario debe mostrar un alert con el mensaje del guard
    const alertEl = page.getByRole("alert");
    await expect(alertEl).toBeVisible({ timeout: NAV_TIMEOUT });
    const alertText = await alertEl.textContent();

    // El mensaje del guard debe mencionar "campeonato" o "único evento"
    expect(
      (alertText ?? "").toLowerCase().includes("campeonato") ||
        (alertText ?? "").toLowerCase().includes("único evento") ||
        (alertText ?? "").toLowerCase().includes("unico evento"),
    ).toBe(true);

    // La URL debe seguir en /competitions/new (no navegó al detalle)
    expect(page.url()).toContain("/competitions/new");
  });
});

// ---------------------------------------------------------------------------
// E2E-014-005: Detalle de una válida de copa — tab Clasificación SÍ existe
// Detalle de campeonato — tab Clasificación NO existe
// ---------------------------------------------------------------------------

test.describe("spec 014 — Detalle: tabs copa vs campeonato", () => {
  test("E2E-014-005a: detalle de una válida de copa (id=5) muestra tab Clasificación y NO badge CD", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto(`/competitions/${CUP_RACE_EVENT_ID}`);

    // El detalle carga
    await expect(page.getByTestId("competition-title")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // La válida de copa (id=5) NO debe tener el badge "CD"
    await expect(page.getByTestId("badge-championship")).toHaveCount(0, {
      timeout: NAV_TIMEOUT,
    });

    // El tab "Clasificación" EXISTE para copas
    await expect(
      page.getByRole("tab", { name: /clasificación/i }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
  });

  test("E2E-014-005b: detalle de un campeonato existente muestra badge CD y NO tiene tab Clasificación", async ({
    page,
  }) => {
    await loginAsCoach(page);

    // Obtener el ID del campeonato via API directa (no asumir navegación de lista)
    const token = await getTokenFromSession(page);
    const eventsDataStr = await page.evaluate(
      async ([url, tok]) => {
        try {
          const resp = await fetch(
            `${url}/api/race-analysis/race-events/?include_championship=true`,
            { headers: { Authorization: `Bearer ${tok}` } },
          );
          return JSON.stringify(await resp.json());
        } catch {
          return "{}";
        }
      },
      [BACKEND, token] as [string, string],
    );

    const eventsData = JSON.parse(eventsDataStr) as {
      items?: { id: number; is_championship: boolean; series_id: number }[];
    };
    const champEvent = (eventsData.items ?? []).find(
      (e) => e.is_championship && e.series_id === CHAMPIONSHIP_SERIES_ID,
    );

    if (!champEvent) {
      test.skip(
        true,
        "No hay evento de campeonato creado aún — ejecutar E2E-014-003 primero o crear uno manualmente.",
      );
      return;
    }

    // Navegar al detalle del campeonato
    await page.goto(`/competitions/${champEvent.id}`);

    // El detalle carga
    await expect(page.getByTestId("competition-title")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // El badge "CD" está presente (is_championship=true)
    await expect(page.getByTestId("badge-championship")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // El tab "Clasificación" NO debe existir para campeonatos (spec 014)
    await expect(
      page.getByRole("tab", { name: /clasificación/i }),
    ).toHaveCount(0, { timeout: NAV_TIMEOUT });

    // Los demás tabs sí deben existir: Información, Resultados, Condiciones, Atletas, Insights IA
    await expect(
      page.getByRole("tab", { name: /información/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: /resultados/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("tab", { name: /condiciones/i }),
    ).toBeVisible();
  });
});

// ---------------------------------------------------------------------------
// E2E-014-006: ImportWizard — cambiar kind a "championship" oculta
// wizard-valida-num y muestra wizard-championship-notice
// series_name está vacío (no hardcodeado a "Copa Valle")
// ---------------------------------------------------------------------------

test.describe("spec 014 — ImportWizard type-aware", () => {
  test("E2E-014-006: ImportWizard — cambiar a campeonato oculta Válida # y muestra aviso; series_name vacío por defecto", async ({
    page,
  }) => {
    await loginAsCoach(page);

    await page.goto("/competitions/import");

    // El wizard carga
    await expect(page.getByTestId("import-wizard")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // El wizard está en step 1
    await expect(page.getByTestId("import-wizard-step1")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // El selector de tipo existe con valor por defecto "cup"
    const kindSelect = page.getByTestId("wizard-series-kind");
    await expect(kindSelect).toBeVisible();
    await expect(kindSelect).toHaveValue("cup");

    // Para copa: el campo "Válida #" es visible
    await expect(page.getByTestId("wizard-valida-num")).toBeVisible();

    // El campo series_name está VACÍO (no hardcodeado a "Copa Valle")
    const seriesNameInput = page.getByTestId("wizard-series-name");
    await expect(seriesNameInput).toBeVisible();
    await expect(seriesNameInput).toHaveValue("");

    // El aviso de campeonato NO está visible cuando el tipo es "copa"
    await expect(
      page.getByTestId("wizard-championship-notice"),
    ).toHaveCount(0);

    // Cambiar a "Campeonato"
    await kindSelect.selectOption("championship");

    // "Válida #" se OCULTA para campeonato
    await expect(page.getByTestId("wizard-valida-num")).toHaveCount(0, {
      timeout: NAV_TIMEOUT,
    });

    // El aviso de "evento único anual" APARECE
    await expect(
      page.getByTestId("wizard-championship-notice"),
    ).toBeVisible({ timeout: NAV_TIMEOUT });

    // El aviso contiene el texto esperado
    await expect(
      page.getByTestId("wizard-championship-notice"),
    ).toContainText(/único/i);

    // El series_name sigue vacío (el cambio de kind no lo rellena)
    await expect(seriesNameInput).toHaveValue("");

    // Volver a copa restaura "Válida #"
    await kindSelect.selectOption("cup");
    await expect(page.getByTestId("wizard-valida-num")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(
      page.getByTestId("wizard-championship-notice"),
    ).toHaveCount(0);
  });
});
