/**
 * E2E spec 016 — Race Analysis Championship Charts Fix
 *
 * Cubre los acceptance criteria de spec 016: seleccionar un campeonato
 * en el picker de Distribución NO produce un error 500; el campeonato
 * aparece como punto DISTINTO en la gráfica de Evolución.
 *
 * Stack real (no mocks):
 *   - Backend FastAPI en http://localhost:8000 (migración b1c2d3e4f5a6 aplicada).
 *   - Frontend Vite en http://localhost:5173 (reuseExistingServer).
 *
 * Seed relevante (seed.py del entorno dev/Docker):
 *   - Serie id=2 "Copa Valle de Ciclomontañismo" (kind=cup)
 *     · Válida I  — event_id=91  (sequence_number=1, location=Sevilla)
 *   - Serie id=4 "Campeonato Departamental 2026" (kind=championship)
 *     · Cto. Dep. — event_id=200 (sequence_number=1, is_championship=true)
 *   - Al menos 1 atleta con race_results en ambos eventos (descubierto vía API).
 *
 * Regresión cubierta:
 *   - Antes del fix: GET /race-analysis/distribution?event_id=<championship_id>
 *     devolvía HTTP 500. El assert E2E-016-001 verificaba que seleccionar
 *     el campeonato en el picker NO produce role="alert" con fallo.
 *   - Antes del fix: la gráfica de Evolución colapsaba copa y campeonato
 *     en el mismo punto porque ambos tienen sequence_number=1.
 *     El assert E2E-016-003 verifica dos labels distintos.
 *
 * Privacidad: NUNCA se hardcodean nombres ni DOB de menores.
 * Los asserts son estructurales: data-testid, roles, texto de UI, conteos.
 *
 * Patrón de aprovisionamiento de datos:
 *   Siguiendo exactamente el patrón de cup-vs-championship.spec.ts,
 *   se usan las credenciales del seed real (entorno dev/Docker) y se
 *   consulta el API para descubrir los IDs dinámicamente. No se usan
 *   page.route() mocks ya que cup-vs-championship.spec.ts no los usa.
 */
import { test, expect, type Page } from "@playwright/test";

// ---------------------------------------------------------------------------
// Credenciales seed (entorno dev/Docker — NUNCA producción)
// ---------------------------------------------------------------------------

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const BACKEND = "http://localhost:8000";

// Texto del picker que identifica la opción "Temporada (todas)"
const SEASON_AGGREGATE_LABEL = "Temporada (todas)";

// Timeouts — tolerancia a cold-start del backend (primera query a MySQL)
const COLD_START_TIMEOUT = 90_000;
const NAV_TIMEOUT = 30_000;

// ---------------------------------------------------------------------------
// Helpers de login — mismo patrón que cup-vs-championship.spec.ts
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
 * Mismo helper que en cup-vs-championship.spec.ts.
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

/**
 * Descubre un atleta con participaciones en race_results.
 *
 * Consulta GET /api/athletes (coach puede ver su club) y luego
 * GET /api/athletes/{id}/race-analysis/races para encontrar uno
 * que tenga al menos 1 carrera en la temporada actual.
 *
 * Devuelve null si el seed no tiene atletas con resultados.
 */
async function findAthleteWithRaces(
  page: Page,
  token: string,
  season: number,
): Promise<{ athleteId: number; raceItems: RaceParticipationItem[] } | null> {
  // Obtener lista de atletas del club
  const athletesStr = await page.evaluate(
    async ([url, tok]) => {
      try {
        const resp = await fetch(`${url}/api/athletes`, {
          headers: { Authorization: `Bearer ${tok}` },
        });
        if (!resp.ok) return "[]";
        const data = await resp.json() as { items?: unknown[] };
        return JSON.stringify(data.items ?? []);
      } catch {
        return "[]";
      }
    },
    [BACKEND, token] as [string, string],
  );

  const athletes = JSON.parse(athletesStr) as { id: number }[];
  if (athletes.length === 0) return null;

  // Buscar el primer atleta con al menos 1 carrera en la temporada
  for (const athlete of athletes.slice(0, 10)) {
    const racesStr = await page.evaluate(
      async ([url, tok, aid, s]) => {
        try {
          const resp = await fetch(
            `${url}/api/athletes/${aid}/race-analysis/races?season=${s}`,
            { headers: { Authorization: `Bearer ${tok}` } },
          );
          if (!resp.ok) return "[]";
          const data = await resp.json() as { items?: unknown[] };
          return JSON.stringify(data.items ?? []);
        } catch {
          return "[]";
        }
      },
      [BACKEND, token, athlete.id, season] as [string, string, number, number],
    );

    const raceItems = JSON.parse(racesStr) as RaceParticipationItem[];
    if (raceItems.length > 0) {
      return { athleteId: athlete.id, raceItems };
    }
  }

  return null;
}

interface RaceParticipationItem {
  event_id: number;
  sequence_number: number;
  series_kind: "cup" | "championship";
  event_date: string;
  event_name: string;
  location: string | null;
  label: string;
}

// ---------------------------------------------------------------------------
// E2E-016-001: Seleccionar el campeonato en el picker de Distribución NO
// produce un error (la regresión: antes del fix devolvía HTTP 500).
// ---------------------------------------------------------------------------

test.describe("spec 016 — Distribución: seleccionar campeonato no falla", () => {
  test("E2E-016-001: seleccionar el campeonato en el picker de Distribución no produce role=alert ni excepción", async ({
    page,
  }) => {
    await loginAsCoach(page);

    const token = await getTokenFromSession(page);
    const season = new Date().getFullYear();

    const result = await findAthleteWithRaces(page, token, season);

    if (!result) {
      test.skip(
        true,
        "No se encontró ningún atleta con race_results en el seed — seed incompleto o temporada sin datos.",
      );
      return;
    }

    const { athleteId, raceItems } = result;

    // Buscar una opción de tipo championship en las carreras disponibles
    const championshipRace = raceItems.find(
      (r) => r.series_kind === "championship",
    );

    if (!championshipRace) {
      test.skip(
        true,
        `El atleta id=${athleteId} no tiene un evento de campeonato en el seed (season=${season}). Requiere que exista un race_result asociado al Campeonato Departamental.`,
      );
      return;
    }

    // Navegar al perfil del atleta, tab Análisis IA
    await page.goto(`/athletes/${athleteId}?tab=ai_analysis`);

    // El tab AI carga
    await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // Navegar al sub-tab Distribución
    await page.getByTestId("ai-subtab-distribution").click();

    // Esperar que el picker de carrera esté disponible (data-testid=distribution-valida-select
    // aparece solo cuando racesQuery.isLoading=false)
    await expect(page.getByTestId("distribution-valida-select")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // El picker inicial debe ser "Temporada (todas)" — opción agregada
    const validaSelect = page.getByTestId("distribution-valida-select");
    await expect(validaSelect).toHaveValue("season-aggregate");

    // Verificar que el campeonato existe como opción en el picker
    const championshipOptionValue = String(championshipRace.event_id);
    const options = await validaSelect.locator("option").allTextContents();
    const hasChampionshipOption = options.some(
      (t) =>
        t.toLowerCase().includes("cto.") ||
        t.toLowerCase().includes("campeonato") ||
        t.toLowerCase().includes("cd"),
    );
    expect(hasChampionshipOption).toBe(true);

    // Seleccionar el campeonato
    await validaSelect.selectOption(championshipOptionValue);

    // Esperar que la consulta se resuelva (spinner desaparece o dato carga)
    // El assert principal: NO debe aparecer role="alert" con fallo de carga
    // Damos tiempo suficiente para que el spinner complete
    await page.waitForTimeout(3000);

    // ASSERT PRINCIPAL — sin error de carga
    // El componente muestra role="alert" solo si query.isError=true
    const alerts = page.locator('[role="alert"]');
    const alertCount = await alerts.count();

    if (alertCount > 0) {
      const alertTexts = await alerts.allTextContents();
      // Fallar explícitamente mostrando el texto del error
      expect(
        alertTexts.join(" | "),
        `Seleccionar el campeonato (event_id=${championshipRace.event_id}) produjo un error: ${alertTexts.join(" | ")}`,
      ).toBe("");
    }

    // ASSERT SECUNDARIO — o hay datos O hay estado de "no corrió esta válida"
    // ambos son estados válidos (el atleta puede no haber competido en el campeonato)
    const hasDistributionContent =
      (await page.locator('[data-testid="distribution-chart"]').count()) > 0;
    expect(
      hasDistributionContent,
      "El contenedor distribution-chart debe seguir presente tras seleccionar el campeonato",
    ).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// E2E-016-002: Seleccionar "Temporada (todas)" muestra el mensaje informativo
// y NO un spinner ni error.
// ---------------------------------------------------------------------------

test.describe("spec 016 — Distribución: estado Temporada (todas) es informativo", () => {
  test("E2E-016-002: seleccionar 'Temporada (todas)' muestra mensaje informativo y no error/spinner", async ({
    page,
  }) => {
    await loginAsCoach(page);

    const token = await getTokenFromSession(page);
    const season = new Date().getFullYear();

    const result = await findAthleteWithRaces(page, token, season);

    if (!result) {
      test.skip(
        true,
        "No se encontró ningún atleta con race_results en el seed.",
      );
      return;
    }

    const { athleteId } = result;

    // Navegar al perfil del atleta, tab Análisis IA
    await page.goto(`/athletes/${athleteId}?tab=ai_analysis`);

    await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // Navegar al sub-tab Distribución
    await page.getByTestId("ai-subtab-distribution").click();

    // Esperar que el picker esté disponible
    await expect(page.getByTestId("distribution-valida-select")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // El picker ya debe estar en "Temporada (todas)" por defecto.
    // Si se llegó aquí desde un estado previo donde se cambió, restaurar.
    const validaSelect = page.getByTestId("distribution-valida-select");
    const currentVal = await validaSelect.inputValue();

    if (currentVal !== "season-aggregate") {
      // Seleccionar la opción agregada
      const options = await validaSelect.locator("option").all();
      for (const opt of options) {
        const val = await opt.getAttribute("value");
        const text = await opt.textContent();
        if (val === "season-aggregate" || (text ?? "").includes(SEASON_AGGREGATE_LABEL)) {
          await validaSelect.selectOption(val ?? "season-aggregate");
          break;
        }
      }
    }

    // ASSERT: Mensaje informativo presente
    // El componente muestra "La distribución se calcula por carrera…" cuando
    // isAggregateOption(selectedValue) === true y hasNoRaces === false.
    await expect(
      page.getByText(/La distribución se calcula por carrera/i),
    ).toBeVisible({ timeout: NAV_TIMEOUT });

    // ASSERT: Sin error ni spinner de distribución activo
    // role="alert" con contenido de error NO debe existir
    const errorAlerts = page.locator('[role="alert"]');
    const alertCount = await errorAlerts.count();
    expect(
      alertCount,
      `No debe haber role="alert" visible al seleccionar "Temporada (todas)". Texto: ${await errorAlerts.allTextContents()}`,
    ).toBe(0);

    // ASSERT: Sin spinner de distribución activo (Cargando distribución)
    await expect(
      page.locator('[aria-label="Cargando distribución"]'),
    ).toHaveCount(0);
  });
});

// ---------------------------------------------------------------------------
// E2E-016-003: Gráfica de Evolución — el campeonato aparece como punto
// DISTINTO a la Válida I (mismo sequence_number=1 pero distinto event_id).
// Dos labels distintos deben estar en el DOM.
// ---------------------------------------------------------------------------

test.describe("spec 016 — Evolución: campeonato es punto distinto a Válida I", () => {
  test("E2E-016-003: la gráfica de Evolución tiene al menos dos labels distintos cuando hay copa y campeonato en la temporada", async ({
    page,
  }) => {
    await loginAsCoach(page);

    const token = await getTokenFromSession(page);
    const season = new Date().getFullYear();

    const result = await findAthleteWithRaces(page, token, season);

    if (!result) {
      test.skip(
        true,
        "No se encontró ningún atleta con race_results en el seed.",
      );
      return;
    }

    const { athleteId, raceItems } = result;

    // Para este test necesitamos que el atleta tenga TANTO una copa COMO un campeonato
    const hasCup = raceItems.some((r) => r.series_kind === "cup");
    const hasChampionship = raceItems.some(
      (r) => r.series_kind === "championship",
    );

    if (!hasCup || !hasChampionship) {
      test.skip(
        true,
        `El atleta id=${athleteId} no tiene participaciones en ambos tipos (cup=${hasCup}, championship=${hasChampionship}). Para verificar la distinción de puntos se necesitan los dos tipos en la misma temporada.`,
      );
      return;
    }

    // Navegar al perfil del atleta, tab Análisis IA
    await page.goto(`/athletes/${athleteId}?tab=ai_analysis`);

    await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({
      timeout: COLD_START_TIMEOUT,
    });

    // Navegar al sub-tab Evolución
    await page.getByTestId("ai-subtab-evolution").click();

    // El chart de evolución carga
    await expect(page.getByTestId("evolution-chart")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // Esperar que el spinner desaparezca
    await expect(
      page.locator('[aria-label="Cargando evolución"]'),
    ).toHaveCount(0, { timeout: NAV_TIMEOUT });

    // ASSERT: sin error de carga de evolución
    await expect(
      page.locator('[role="alert"]'),
    ).toHaveCount(0, { timeout: NAV_TIMEOUT });

    // ASSERT PRINCIPAL — la leyenda accesible expone los labels en el DOM.
    // EvolutionChart.tsx renderiza un <ol aria-label="Etiquetas del eje de evolución">
    // con un <li> por cada punto del chartData. El campeonato tiene series_kind="championship"
    // y su li tiene clase "font-medium text-amber-700".
    const legendList = page.getByRole("list", {
      name: /etiquetas del eje de evolución/i,
    });
    await expect(legendList).toBeVisible({ timeout: NAV_TIMEOUT });

    const legendItems = legendList.getByRole("listitem");
    const count = await legendItems.count();

    // Debe haber al menos 2 puntos (Válida I de copa + campeonato)
    expect(
      count,
      "La leyenda de evolución debe tener al menos 2 puntos (copa + campeonato)",
    ).toBeGreaterThanOrEqual(2);

    // Todos los textos de la leyenda
    const labelTexts = await legendItems.allTextContents();

    // El campeonato debe estar presente con su label "Cto. Dep." / "CD" / variante
    // El backend genera labels como "Cto. Dep. — Ginebra" para championships.
    const hasChampionshipLabel = labelTexts.some(
      (t) =>
        t.toLowerCase().includes("cto.") ||
        t.toLowerCase().includes("campeonato") ||
        t.toLowerCase().includes(" cd"),
    );
    expect(
      hasChampionshipLabel,
      `La leyenda debe contener un label del campeonato. Labels encontrados: ${labelTexts.join(", ")}`,
    ).toBe(true);

    // ASSERT DE DISTINCIÓN — los labels deben ser únicos (no colapsados).
    // La regresión colapsaba copa y campeonato en el mismo punto porque ambos
    // tenían sequence_number=1; el fix usa event_id como key en chartData.
    const uniqueLabels = new Set(labelTexts);
    expect(
      uniqueLabels.size,
      `Los labels del eje deben ser únicos. Labels: ${labelTexts.join(", ")}`,
    ).toBe(count);

    // ASSERT DE ORDEN — el campeonato debe aparecer en fecha posterior a Válida I.
    // El seed tiene Válida I en enero y el Campeonato en junio.
    // Verificamos que el campeonato NO es el primer punto de la leyenda
    // cuando hay una copa antes.
    const firstCupInRaces = raceItems
      .filter((r) => r.series_kind === "cup")
      .sort(
        (a, b) =>
          new Date(a.event_date).getTime() - new Date(b.event_date).getTime(),
      )[0];
    const championshipInRaces = raceItems.find(
      (r) => r.series_kind === "championship",
    )!;

    const cupBeforeChampionship =
      new Date(firstCupInRaces.event_date).getTime() <
      new Date(championshipInRaces.event_date).getTime();

    if (cupBeforeChampionship) {
      // El primer item de la leyenda NO debe ser el campeonato
      const firstLabelText = labelTexts[0] ?? "";
      const firstLabelIsChampionship =
        firstLabelText.toLowerCase().includes("cto.") ||
        firstLabelText.toLowerCase().includes("campeonato");

      expect(
        firstLabelIsChampionship,
        `El primer punto de la leyenda no debería ser el campeonato cuando la Válida I ocurrió antes (${firstCupInRaces.event_date} < ${championshipInRaces.event_date}). Primer label: "${firstLabelText}"`,
      ).toBe(false);
    }
  });
});
