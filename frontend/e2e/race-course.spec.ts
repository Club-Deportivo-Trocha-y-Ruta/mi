/**
 * E2E spec — feature 043 (race course profile), Playwright part 1 (T030).
 *
 * Cubre `ui-course.md` §8 (parte 1) y `quickstart.md` §6 pasos 1–3: subir dos
 * variantes de circuito (GPX sintético → detección de vueltas →
 * confirmación), configurar vueltas por categoría y verificar que ambas
 * cosas persisten tras recargar la página. La parte 2 (descripción
 * cualitativa, tab Resultados, vista del padre) es una fase posterior
 * (T043+, T058+) — no cubierta aquí.
 *
 * VITE_API_BASE_URL — nota VERBATIM de `playwright.config.ts` (léela ahí
 * antes de tocar esta spec o ese archivo):
 *   "Los specs interceptan con `page.route()` filtrando por `url.port !==
 *   "5173"` (o `E2E_APP_PORT` cuando está definido) — es decir asumen que el
 *   front llama al backend por URL absoluta (:8000, o `E2E_API_BASE_URL`).
 *   Un `.env.local` con `VITE_API_BASE_URL=` (cadena vacía) rompe ese
 *   supuesto: `??` en src/api/client.ts solo cae al default con
 *   null/undefined, así que la cadena vacía deja el baseURL relativo, las
 *   peticiones salen por el proxy de Vite y ningún `page.route()` las
 *   intercepta. Fijar la variable aquí hace la suite e2e autónoma sin tocar
 *   la configuración de desarrollo local."
 *
 * Stack real (mismo patrón que `competitions-unification.spec.ts` /
 * `cup-vs-championship.spec.ts` / `prefill-import-from-competition.spec.ts`):
 * sin mocks de `page.route()`, corre contra un backend FastAPI real + MySQL.
 * `BACKEND` abajo asume `:8000` (el mismo supuesto que esos specs hermanos);
 * para la pila aislada (`docker-compose.e2e.yml`, backend en `:8001`) hay que
 * ajustarlo junto con `E2E_APP_PORT`/`E2E_API_BASE_URL` — no lo hicieron
 * tampoco los specs hermanos, así que se deja igual por consistencia.
 *
 * Datos: esta spec NO depende del seed para la parte de variantes — crea su
 * propia serie tipo copa y su propia válida por API directa antes de tocar
 * la UI (mismo patrón "setup por API, verificación por UI" que
 * `prefill-import-from-competition.spec.ts`), así que es repetible sin
 * importar qué haya en el seed ni en corridas previas.
 *
 * GAP CONOCIDO (repetido en el reporte de T030 — no es un atajo de esta
 * spec, es una lectura del código real): `CourseTab.tsx` NO pasa
 * `resultCategoryIds` a `CategorySetupTable` — compárese el comentario de la
 * tarea T024 en `tasks.md` ("rows = categories in results ∪ setups ∪
 * suggested") con la composición real que arma T025, que omite esa prop por
 * completo. Consecuencia: una válida nueva, sin `setups` propios y sin una
 * válida anterior en la misma serie con `setups` guardados, SIEMPRE muestra
 * "No hay categorías disponibles para configurar todavía" — incluso si esa
 * válida ya tiene resultados importados con categorías reales. Esta spec no
 * puede ejercitar "el coach descubre una categoría desde los resultados y le
 * pone vueltas por primera vez" porque ese camino no existe todavía en la
 * UI. En su lugar: descubre un `category_id` real desde los resultados de
 * CUALQUIER válida completada existente en el entorno (el id es una FK al
 * catálogo GLOBAL `race_categories` — contrato `course-api.md` §5:
 * "Categories are not required to have results in the válida" — así que es
 * válido usarlo en la válida nueva de esta spec), siembra con él una fila
 * inicial vía `PUT .../course/setups` por API directa, y LUEGO edita esa
 * fila vía UI real (cambia las vueltas, guarda, recarga, verifica). Si el
 * entorno no tiene ninguna válida completada con resultados, la sección de
 * setups se salta con `test.skip` y motivo explícito — no se fabrica nada.
 *
 * RIESGO DE CARRERA DETECTADO AL LEER EL CÓDIGO (no se puede confirmar sin
 * ejecutar esta spec contra el stack real, así que queda documentado aquí
 * para quien la corra por primera vez): el `onSuccess` de
 * `useUploadCourseVariant` invalida la query `["race-course", id]` ANTES de
 * que el `onSuccess` local de `VariantUploadDialog` ponga `stage` en
 * "question". Esa invalidación dispara un refetch real (un GET, no
 * instantáneo); cuando resuelve, `CourseTab` pasa de la rama
 * `!has_course_data` (que incluye el propio diálogo de confirmación) a la
 * rama `has_course_data` (que monta `VariantsCard` con su PROPIO diálogo,
 * cerrado) — desmontando en el camino el diálogo que está mostrando la
 * pregunta de detección. Si esta spec falla de forma intermitente justo en
 * la aserción de `variant-upload-question` de la PRIMERA variante (la única
 * que dispara esa transición empty→con-datos), esa carrera es la causa más
 * probable, no un defecto del test.
 *
 * Privacidad: sin nombres ni fechas de nacimiento de menores en ningún
 * literal de esta spec; los GPX subidos son sintéticos (nunca la grabación
 * real de un coach) — ver `frontend/e2e/fixtures/README.md`.
 */
import { fileURLToPath } from "node:url";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const BACKEND = "http://localhost:8000";

const COLD_START_TIMEOUT = 90_000;
const NAV_TIMEOUT = 30_000;

const FIXTURES_DIR = path.join(
  path.dirname(fileURLToPath(import.meta.url)),
  "fixtures",
);
const COURSE_3LAPS_GPX = path.join(FIXTURES_DIR, "course_3laps.gpx");
const COURSE_REDUCED_GPX = path.join(FIXTURES_DIR, "course_reduced.gpx");

// ---------------------------------------------------------------------------
// Login — mismo patrón que competitions-unification.spec.ts
// ---------------------------------------------------------------------------

async function loginAsCoach(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(COACH.email);
  await page
    .getByRole("textbox", { name: /contraseña/i })
    .fill(COACH.password);
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

async function getToken(page: Page): Promise<string> {
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
// Setup de datos vía API directa — serie + válida propias (no dependen del
// seed), mismo patrón de "descubrir/crear por API, verificar por UI" que
// `prefill-import-from-competition.spec.ts` / `cup-vs-championship.spec.ts`.
// ---------------------------------------------------------------------------

async function createCupSeries(page: Page, token: string): Promise<number> {
  return page.evaluate(
    async ({ backend, t, body }) => {
      const res = await fetch(`${backend}/api/race-analysis/race-series/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${t}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`createCupSeries: HTTP ${res.status}`);
      }
      const data = (await res.json()) as { id: number };
      return data.id;
    },
    {
      backend: BACKEND,
      t: token,
      body: {
        name: `E2E Circuito ${Date.now()}`,
        season_year: new Date().getFullYear(),
        kind: "cup",
      },
    },
  );
}

async function createRaceEvent(
  page: Page,
  token: string,
  seriesId: number,
): Promise<number> {
  return page.evaluate(
    async ({ backend, t, body }) => {
      const res = await fetch(`${backend}/api/race-analysis/race-events/`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${t}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        throw new Error(`createRaceEvent: HTTP ${res.status}`);
      }
      const data = (await res.json()) as { id: number };
      return data.id;
    },
    {
      backend: BACKEND,
      t: token,
      body: {
        series_id: seriesId,
        sequence_number: 1,
        name: `E2E Circuito — válida de prueba ${Date.now()}`,
        // Fecha futura respecto a la fecha de esta spec: evita que
        // CompetitionDetailPage muestre la CTA primaria "Importar
        // resultados" (showImportCTA exige fecha ya pasada), que no aporta
        // nada a este flujo y solo agrega ruido a la página.
        event_date: "2026-12-01",
        status: "scheduled",
        create_calendar_event: false,
      },
    },
  );
}

/**
 * Descubre un `category_id` real desde los resultados de alguna válida ya
 * completada en este entorno — nunca hardcodeado (mismo principio que
 * `discoverEventIds` en `prefill-import-from-competition.spec.ts`).
 * `category_id` es una FK al catálogo GLOBAL `race_categories`, no algo
 * propio de una válida (contrato `course-api.md` §5), así que un id
 * descubierto en CUALQUIER válida es válido para sembrar un setup en la
 * válida nueva que crea esta spec.
 *
 * Devuelve `null` si no hay ninguna válida completada con resultados en este
 * entorno — la spec salta la sección de "vueltas por categoría" en ese caso
 * (ver el GAP CONOCIDO documentado en el encabezado del archivo).
 */
async function discoverCategoryId(
  page: Page,
  token: string,
): Promise<number | null> {
  return page.evaluate(
    async ({ backend, t }) => {
      const listRes = await fetch(
        `${backend}/api/race-analysis/race-events/?status=completed`,
        { headers: { Authorization: `Bearer ${t}` } },
      );
      if (!listRes.ok) return null;
      const listData = (await listRes.json()) as {
        items?: { id: number; has_results?: boolean }[];
      };
      const candidates = (listData.items ?? []).filter(
        (e) => e.has_results !== false,
      );

      for (const ev of candidates.slice(0, 25)) {
        const resultsRes = await fetch(
          `${backend}/api/race-analysis/race-events/${ev.id}/results`,
          { headers: { Authorization: `Bearer ${t}` } },
        );
        if (!resultsRes.ok) continue;
        const resultsData = (await resultsRes.json()) as {
          categories?: { category_id: number }[];
        };
        const first = (resultsData.categories ?? [])[0];
        if (first) return first.category_id;
      }
      return null;
    },
    { backend: BACKEND, t: token },
  );
}

interface CourseVariantApi {
  id: number;
  label: string;
}

async function fetchCourseVariants(
  page: Page,
  token: string,
  raceEventId: number,
): Promise<CourseVariantApi[]> {
  return page.evaluate(
    async ({ backend, t, id }) => {
      const res = await fetch(
        `${backend}/api/race-analysis/race-events/${id}/course`,
        { headers: { Authorization: `Bearer ${t}` } },
      );
      const data = (await res.json()) as { variants?: CourseVariantApi[] };
      return data.variants ?? [];
    },
    { backend: BACKEND, t: token, id: raceEventId },
  );
}

async function seedInitialSetup(
  page: Page,
  token: string,
  raceEventId: number,
  categoryId: number,
  variantId: number,
  laps: number,
): Promise<void> {
  await page.evaluate(
    async ({ backend, t, id, body }) => {
      const res = await fetch(
        `${backend}/api/race-analysis/race-events/${id}/course/setups`,
        {
          method: "PUT",
          headers: {
            Authorization: `Bearer ${t}`,
            "Content-Type": "application/json",
          },
          body: JSON.stringify(body),
        },
      );
      if (!res.ok) {
        throw new Error(`seedInitialSetup: HTTP ${res.status}`);
      }
    },
    {
      backend: BACKEND,
      t: token,
      id: raceEventId,
      body: {
        setups: [{ category_id: categoryId, laps, variant_id: variantId }],
      },
    },
  );
}

// ---------------------------------------------------------------------------
// E2E-043-001
// ---------------------------------------------------------------------------

test.describe("feature 043 — perfil de circuito (parte 1)", () => {
  test("E2E-043-001: coach sube dos variantes GPX, confirma detección, configura vueltas por categoría y todo persiste tras recargar", async ({
    page,
  }) => {
    await loginAsCoach(page);
    const token = await getToken(page);

    const seriesId = await createCupSeries(page, token);
    const raceEventId = await createRaceEvent(page, token, seriesId);

    // La creación vía UI (CompetitionFormPage, modo create) aterriza directo
    // en `?tab=circuito` (comentario feature 043 / T028 en
    // CompetitionFormPage.tsx) — como esta spec crea la válida por API,
    // navegamos ahí directamente para llegar al mismo punto.
    await page.goto(`/competitions/${raceEventId}?tab=circuito`);

    const courseTab = page.getByTestId("course-tab");
    await expect(courseTab).toBeVisible({ timeout: COLD_START_TIMEOUT });
    await expect(page.getByTestId("course-tab-empty")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // ── Variante 1: "Circuito completo" (course_3laps.gpx → 3 vueltas) ────
    await page.getByTestId("course-tab-add-variant-btn").click();

    const labelInput1 = page.getByTestId("variant-upload-label");
    await expect(labelInput1).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(labelInput1).toHaveValue("Circuito completo");

    await page
      .getByTestId("variant-upload-file")
      .setInputFiles(COURSE_3LAPS_GPX);
    await page.getByTestId("variant-upload-submit").click();

    // Detección closed_loop de 3 vueltas → pregunta de confirmación (ver
    // "RIESGO DE CARRERA" documentado en el encabezado si esto es
    // intermitente en la ejecución real).
    const question = page.getByTestId("variant-upload-question");
    await expect(question).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(question).toContainText(/3 vueltas/);

    await page.getByTestId("variant-upload-confirm").click(); // "Sí, guardar"
    await expect(page.getByTestId("variant-upload-success")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await page.getByTestId("variant-upload-close").click();

    await expect(page.getByTestId("course-variants-card")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(
      page.locator('[data-testid^="course-variant-row-"]'),
    ).toHaveCount(1, { timeout: NAV_TIMEOUT });

    // ── Variante 2: "Recorrido reducido" (course_reduced.gpx → 1 vuelta) ──
    await page.getByTestId("course-variants-add-btn").click();

    const labelInput2 = page.getByTestId("variant-upload-label");
    await expect(labelInput2).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(labelInput2).toHaveValue("Recorrido reducido");

    await page
      .getByTestId("variant-upload-file")
      .setInputFiles(COURSE_REDUCED_GPX);
    await page.getByTestId("variant-upload-submit").click();

    // Detección "single" (no hay una segunda vuelta que cierre): va directo
    // a éxito, SIN pregunta — copy distinta de la variante 1 (ui-course.md
    // §2: "single" no pregunta).
    await expect(page.getByTestId("variant-upload-question")).toHaveCount(0);
    await expect(page.getByTestId("variant-upload-success")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await page.getByTestId("variant-upload-close").click();

    await expect(
      page.locator('[data-testid^="course-variant-row-"]'),
    ).toHaveCount(2, { timeout: NAV_TIMEOUT });

    // ── Vueltas por categoría ──────────────────────────────────────────
    // Ver el GAP CONOCIDO documentado en el encabezado del archivo: se
    // descubre un category_id real desde los resultados de una válida
    // completada existente y se siembra una fila inicial por API, porque la
    // UI actual no tiene forma de mostrar una fila de categoría "desde
    // cero" en una válida nueva (CourseTab no pasa `resultCategoryIds`).
    const categoryId = await discoverCategoryId(page, token);
    test.skip(
      categoryId == null,
      "No hay ninguna válida completada con resultados en este entorno: " +
        "CategorySetupTable no puede mostrar ninguna fila de categoría sin " +
        "una (gap conocido: CourseTab no pasa `resultCategoryIds`; ver " +
        "encabezado de este archivo y el reporte de T030).",
    );

    const variants = await fetchCourseVariants(page, token, raceEventId);
    const circuitoCompleto = variants.find(
      (v) => v.label === "Circuito completo",
    );
    expect(
      circuitoCompleto,
      "la variante 'Circuito completo' debe existir tras el upload",
    ).toBeTruthy();
    const variantId = circuitoCompleto!.id;

    // Siembra un valor inicial (2 vueltas) — la spec lo CAMBIA a continuación
    // vía UI real, para probar guardado + persistencia y no solo lectura.
    await seedInitialSetup(page, token, raceEventId, categoryId!, variantId, 2);

    await page.reload();
    await expect(courseTab).toBeVisible({ timeout: NAV_TIMEOUT });

    const setupRow = page.getByTestId(`course-setup-row-${categoryId}`);
    await expect(setupRow).toBeVisible({ timeout: NAV_TIMEOUT });
    const lapsInput = page.getByTestId(`course-setup-laps-${categoryId}`);
    await expect(lapsInput).toHaveValue("2");

    await lapsInput.fill("3");
    await page.getByTestId("course-setup-save").click();
    await expect(page.getByTestId("course-setup-error")).toHaveCount(0, {
      timeout: NAV_TIMEOUT,
    });

    // ── Recarga: re-consultar el DOM, no confiar en estado en memoria ────
    await page.reload();
    await expect(courseTab).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(
      page.locator('[data-testid^="course-variant-row-"]'),
    ).toHaveCount(2, { timeout: NAV_TIMEOUT });
    await expect(
      page.getByTestId(`course-setup-laps-${categoryId}`),
    ).toHaveValue("3", { timeout: NAV_TIMEOUT });
  });
});
