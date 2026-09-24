/**
 * E2E spec — feature 043 (race course profile), Playwright part 1 (T030).
 *
 * Cubre `ui-course.md` §8 (parte 1) y `quickstart.md` §6 pasos 1–3: subir dos
 * variantes de circuito (GPX sintético → detección de vueltas →
 * confirmación), configurar vueltas por categoría y verificar que ambas
 * cosas persisten tras recargar la página. La parte 2 (descripción
 * cualitativa, columnas de distancia/velocidad en la tabla de resultados,
 * vista del padre) se agregó más abajo en este mismo archivo (T061) — ver
 * el segundo `test.describe` de este archivo, con su propio encabezado de
 * documentación.
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
 * `BACKEND` abajo lee `E2E_API_BASE_URL` (default `:8000`, igual que el resto
 * de la suite): para la pila aislada (`docker-compose.e2e.yml`, backend en
 * `:8001`) se corre con `E2E_APP_PORT=5175 E2E_API_BASE_URL=http://localhost:8001`.
 * Este spec ESCRIBE (crea series/válidas y sube GPX): nunca apuntarlo al
 * backend real del club.
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
 * Feature 045 (T064): el perfil del circuito vive ahora en la pestaña
 * «Circuito y condiciones» (`?tab=circuito`; el alias legado
 * `?tab=conditions` redirige ahí). Esa pestaña reúne `CourseTab` (bloque
 * «Circuito») y `RaceConditionsCard` (bloque «Condiciones») en la MISMA
 * página, así que los locators de esta spec que antes eran únicos porque
 * las condiciones estaban en otra pestaña (Radix desmonta la inactiva)
 * ahora deben acotarse — p. ej. `getByLabel("Notas")` también casaba con
 * el `aria-label="Sin registro de notas"` de `RaceConditionsCard`, por eso
 * la edición de la descripción se busca dentro de `getByRole("dialog")`.
 *
 * Privacidad: sin nombres ni fechas de nacimiento de menores en ningún
 * literal de esta spec; los GPX subidos son sintéticos (nunca la grabación
 * real de un coach) — ver `frontend/e2e/fixtures/README.md`.
 */
import { fileURLToPath } from "node:url";
import fs from "node:fs";
import path from "node:path";

import { test, expect, type Page } from "@playwright/test";

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const BACKEND = process.env.E2E_API_BASE_URL ?? "http://localhost:8000";

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
    // navegamos ahí directamente para llegar al mismo punto. Desde la
    // feature 045 esa pestaña se llama «Circuito y condiciones».
    await page.goto(`/competitions/${raceEventId}?tab=circuito`);
    await expect(
      page.getByRole("tab", { name: /circuito y condiciones/i }),
    ).toHaveAttribute("aria-selected", "true", { timeout: COLD_START_TIMEOUT });

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

    // "Sí, guardar" solo CIERRA el sheet (`VariantUploadDialog`: el archivo ya
    // quedó guardado al enviarlo; la etapa `success` con «Cerrar» existe solo
    // para las variantes que no preguntan, p. ej. la 2.ª de abajo). No hay
    // `variant-upload-success` en esta rama.
    await page.getByTestId("variant-upload-confirm").click();
    await expect(page.getByTestId("variant-upload-question")).toHaveCount(0, {
      timeout: NAV_TIMEOUT,
    });

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

/**
 * E2E spec — feature 043 (race course profile), Playwright PARTE 2 (T061).
 *
 * Cubre lo que la parte 1 (arriba) deja explícitamente fuera: `ui-course.md`
 * §8 (parte 2) — ronda de descripción cualitativa vía UI, columnas
 * "Distancia"/"Vel. prom." derivadas de circuito en la tabla de resultados
 * (feature 043 US2, `ResultsTable.tsx`), y la tarjeta de reconocimiento de
 * pista (`CourseSummary`, US5) desde la sesión de un padre — tanto cuando SÍ
 * corresponde mostrarla como cuando NO.
 *
 * Testids/aria-labels usados abajo se tomaron leyendo directamente los
 * componentes ya aterrizados (no se adivinó ninguno):
 *   - `CourseDescriptionCard.tsx` / `EditCourseDescriptionDialog.tsx` (US3,
 *     ya en `main` antes de esta tarea) — `course-description-card-empty`,
 *     `course-description-describe-btn`, `course-description-card-complete`,
 *     radios/checkboxes por `aria-label` (`TERRAIN_TYPE_LABELS` /
 *     `KEY_SECTOR_LABELS` / `DIFFICULTY_LABELS` de
 *     `src/types/raceCourse.types.ts`), textarea vía `getByRole("dialog").getByLabel("Notas", { exact: true })`.
 *   - `CourseSummary.tsx` (T058, landed junto con esta tarea) —
 *     `course-summary`, `course-summary-description-{terrain,difficulty,
 *     sectors,notes}`.
 *   - `ResultsTable.tsx` (US2, ya en `main`) — `results-category-section-
 *     {categoryId}`, encabezados `role="columnheader"` con texto exacto
 *     "Distancia" / "Vel. prom." (mismo criterio que
 *     `ResultsTable.test.tsx`).
 *   - `ParentCompetitionResultsPage.tsx` (T059, landed junto con esta
 *     tarea) — `parent-results-page`.
 *
 * Diferencia deliberada con la parte 1: las funciones de setup de abajo usan
 * `page.request.*` (el cliente HTTP de Playwright, fuera del navegador) en
 * vez de `page.evaluate(() => fetch(...))`. La parte 1 necesitaba el fetch
 * DENTRO de la página porque ya había navegado con una sesión de coach
 * cargada; varias de las llamadas de setup de aquí (login de un segundo rol,
 * lectura del propio atleta del padre) ocurren ANTES de cualquier
 * `page.goto` para ese rol, así que `page.request` evita depender de CORS
 * entre el origen del front (`:5173`) y el backend (`:8000`) para trabajo
 * que es puramente de datos, no de UI.
 *
 * GAP DE DATOS CONOCIDO Y EFECTO SECUNDARIO DELIBERADO (léase antes de correr
 * esta parte por primera vez contra un entorno compartido): el caso
 * "columnas Distancia/Vel. prom." (E2E-043-003) solo puede ejercitarse sobre
 * una válida que YA tenga resultados reales importados — no existe un
 * endpoint para crear un `RaceResult` fuera del pipeline de importación de
 * PDF (`routers/race_imports.py`), y ese pipeline no tiene atajo por API
 * (CLAUDE.md: "Operated through the web Import Wizard ... there is no CLI
 * path"). La spec por tanto DESCUBRE una válida completada existente con
 * resultados (mismo patrón que `discoverCategoryId` de la parte 1, extendido
 * para devolver también el `race_event_id`) y le AGREGA datos de circuito
 * (una variante + una fila de `setups` para una categoría que ya tiene
 * resultados) si todavía no los tiene — un efecto secundario real y
 * persistente sobre esa válida del entorno compartido, no reversible por
 * esta misma spec. Se mitiga así:
 *   - Es idempotente: si ya corrió antes (la variante con la misma etiqueta
 *     ya existe), reutiliza esa variante en vez de volver a subir el mismo
 *     GPX (que devolvería `409 duplicate_recording`, ver `course-api.md`
 *     §2), y si la fila de `setups` ya apunta a esa variante no vuelve a
 *     hacer `PUT`.
 *   - Nunca destruye datos de otras categorías: `PUT /course/setups`
 *     reemplaza la tabla COMPLETA, así que el merge conserva toda fila
 *     existente cuyo `category_id` no sea el que esta spec necesita.
 *   - No toca `description` ni ninguna otra válida del entorno.
 * Aun así, cualquier otra spec que asuma "ninguna válida completada tiene
 * circuito configurado" podría verse afectada al correr después de esta —
 * no se detectó ninguna en este repo al momento de escribir esto, pero
 * queda anotado para quien la ejecute por primera vez contra el entorno
 * real. Si el entorno no tiene ninguna válida completada con resultados,
 * el caso se salta con `test.skip` y motivo explícito, igual que el gap
 * equivalente de la parte 1.
 *
 * Privacidad: la descripción de circuito usada en E2E-043-002 es texto
 * genérico sobre el trazado (sin nombres de atletas ni datos médicos, mismo
 * criterio que exige el placeholder de `EditCourseDescriptionDialog.tsx`).
 * El atleta usado para las pruebas de padre es el fixture sintético
 * "Santiago" de `backend/scripts/seed.py` (vinculado a
 * `padre@trochayruta.com`), el mismo ya usado por `growth-parent.spec.ts` —
 * no un dato real. Las pruebas de padre usan un `browser.newContext()`
 * separado del contexto de coach (en vez de reutilizar `page`), lo que
 * evita cualquier interferencia de `sessionStorage` entre las dos sesiones
 * y refleja con más fidelidad dos usuarios reales en dos dispositivos
 * distintos.
 */

const PARENT_EMAIL = "padre@trochayruta.com";
const PARENT_PASSWORD = "Parent2026!";

/** Mismo patrón que `loginAsCoach` de la parte 1, credenciales de padre
 * sembradas por `backend/scripts/seed.py`. */
async function loginAsParent(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(PARENT_EMAIL);
  await page
    .getByRole("textbox", { name: /contraseña/i })
    .fill(PARENT_PASSWORD);
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

/**
 * Sube una variante de circuito directamente por API (multipart), sin pasar
 * por `VariantUploadDialog` — la UI de subida ya está cubierta por
 * E2E-043-001 (parte 1); aquí el GPX es solo un insumo de setup para probar
 * otra cosa. `course-api.md` §2 confirma que la confirmación de detección es
 * un paso de UI, no de API: el servidor guarda lo que detectó sin pedir
 * confirmación, así que un POST directo es válido incluso para
 * `course_3laps.gpx` — esta spec solo usa `course_reduced.gpx` (detección
 * "single", sin ambigüedad) por simplicidad. Devuelve el `id` de la
 * variante creada.
 */
async function uploadCourseVariantApi(
  page: Page,
  token: string,
  raceEventId: number,
  label: string,
  gpxPath: string,
): Promise<number> {
  const res = await page.request.post(
    `${BACKEND}/api/race-analysis/race-events/${raceEventId}/course/variants`,
    {
      headers: { Authorization: `Bearer ${token}` },
      multipart: {
        file: {
          name: "course.gpx",
          mimeType: "application/gpx+xml",
          buffer: fs.readFileSync(gpxPath),
        },
        label,
      },
    },
  );
  if (!res.ok()) {
    throw new Error(
      `uploadCourseVariantApi: HTTP ${res.status()} — ${await res.text()}`,
    );
  }
  const body = (await res.json()) as { variants: CourseVariantApi[] };
  const variant = body.variants.find((v) => v.label === label);
  if (!variant) {
    throw new Error(
      `uploadCourseVariantApi: no se encontró la variante "${label}" en la respuesta`,
    );
  }
  return variant.id;
}

interface CourseSetupApi {
  category_id: number;
  laps: number;
  variant_id: number;
}

interface CourseFullApi {
  variants: CourseVariantApi[];
  setups: CourseSetupApi[];
}

async function fetchCourseFull(
  page: Page,
  token: string,
  raceEventId: number,
): Promise<CourseFullApi> {
  const res = await page.request.get(
    `${BACKEND}/api/race-analysis/race-events/${raceEventId}/course`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!res.ok()) {
    throw new Error(`fetchCourseFull: HTTP ${res.status()}`);
  }
  return (await res.json()) as CourseFullApi;
}

/** `PUT /course/setups` reemplaza la tabla COMPLETA — el caller es
 * responsable de incluir toda fila que quiera conservar (ver
 * `ensureCourseSetupForResultsColumns`, que arma el merge). */
async function putCourseSetups(
  page: Page,
  token: string,
  raceEventId: number,
  setups: CourseSetupApi[],
): Promise<void> {
  const res = await page.request.put(
    `${BACKEND}/api/race-analysis/race-events/${raceEventId}/course/setups`,
    {
      headers: { Authorization: `Bearer ${token}` },
      data: { setups },
    },
  );
  if (!res.ok()) {
    throw new Error(
      `putCourseSetups: HTTP ${res.status()} — ${await res.text()}`,
    );
  }
}

/**
 * Descubre una válida completada CON al menos una categoría con filas de
 * resultado — a diferencia de `discoverCategoryId` de la parte 1 (que solo
 * necesita un `category_id` válido, de cualquier válida), esta necesita el
 * PAR (`race_event_id`, `category_id`) de la MISMA válida, porque
 * "Distancia"/"Vel. prom." solo se pueden ver en una tabla de resultados que
 * de verdad tenga filas que renderizar. Devuelve `null` si el entorno no
 * tiene ninguna — la spec salta ese caso con `test.skip` (ver GAP DE DATOS
 * en el encabezado de este archivo).
 */
async function discoverCompletedEventWithResults(
  page: Page,
  token: string,
): Promise<{ eventId: number; categoryId: number } | null> {
  const listRes = await page.request.get(
    `${BACKEND}/api/race-analysis/race-events/?status=completed`,
    { headers: { Authorization: `Bearer ${token}` } },
  );
  if (!listRes.ok()) return null;
  const listData = (await listRes.json()) as {
    items?: { id: number; has_results?: boolean }[];
  };
  const candidates = (listData.items ?? []).filter(
    (e) => e.has_results !== false,
  );

  for (const ev of candidates.slice(0, 25)) {
    const resultsRes = await page.request.get(
      `${BACKEND}/api/race-analysis/race-events/${ev.id}/results`,
      { headers: { Authorization: `Bearer ${token}` } },
    );
    if (!resultsRes.ok()) continue;
    const resultsData = (await resultsRes.json()) as {
      categories?: { category_id: number; rows?: unknown[] }[];
    };
    const firstWithRows = (resultsData.categories ?? []).find(
      (c) => (c.rows ?? []).length > 0,
    );
    if (firstWithRows) {
      return { eventId: ev.id, categoryId: firstWithRows.category_id };
    }
  }
  return null;
}

const RESULTS_COLUMNS_VARIANT_LABEL = "Circuito E2E — distancia y velocidad";

/**
 * Garantiza que `raceEventId` tenga datos de circuito (variante + una fila
 * de `setups` para `categoryId`) — idempotente (ver GAP DE DATOS en el
 * encabezado del archivo: no vuelve a subir el GPX si la variante ya existe,
 * no vuelve a hacer `PUT` si la fila ya está correcta, y nunca borra las
 * filas de `setups` de otras categorías).
 */
async function ensureCourseSetupForResultsColumns(
  page: Page,
  token: string,
  raceEventId: number,
  categoryId: number,
): Promise<void> {
  const course = await fetchCourseFull(page, token, raceEventId);

  const existingVariant = course.variants.find(
    (v) => v.label === RESULTS_COLUMNS_VARIANT_LABEL,
  );
  const variantId = existingVariant
    ? existingVariant.id
    : await uploadCourseVariantApi(
        page,
        token,
        raceEventId,
        RESULTS_COLUMNS_VARIANT_LABEL,
        COURSE_REDUCED_GPX,
      );

  const alreadyWired = course.setups.some(
    (s) => s.category_id === categoryId && s.variant_id === variantId,
  );
  if (alreadyWired) return;

  const merged: CourseSetupApi[] = [
    ...course.setups.filter((s) => s.category_id !== categoryId),
    { category_id: categoryId, laps: 1, variant_id: variantId },
  ];
  await putCourseSetups(page, token, raceEventId, merged);
}

// ---------------------------------------------------------------------------
// E2E-043-002 .. E2E-043-005
// ---------------------------------------------------------------------------

test.describe("feature 043 — perfil de circuito (parte 2)", () => {
  test("E2E-043-002: coach edita la descripción cualitativa del circuito vía UI y persiste tras recargar", async ({
    page,
  }) => {
    await loginAsCoach(page);
    const token = await getToken(page);

    const seriesId = await createCupSeries(page, token);
    const raceEventId = await createRaceEvent(page, token, seriesId);

    await page.goto(`/competitions/${raceEventId}?tab=circuito`);
    const courseTab = page.getByTestId("course-tab");
    await expect(courseTab).toBeVisible({ timeout: COLD_START_TIMEOUT });
    // «Circuito y condiciones» monta los dos bloques en la misma página
    // (feature 045): el perfil del circuito y la tarjeta de condiciones.
    await expect(page.getByTestId("circuit-conditions-tab")).toBeVisible();
    await expect(page.getByTestId("conditions-tab")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // Estado vacío (0/4 campos) — coach ve el CTA "Describir la pista"
    // (`CourseDescriptionCard`, US3, ya en `main`).
    await expect(
      page.getByTestId("course-description-card-empty"),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    await page.getByTestId("course-description-describe-btn").click();

    // Sheet de edición (`EditCourseDescriptionDialog`) — los 4 campos son
    // opcionales; se rellenan los 4 para llegar al estado "completo"
    // (`course-description-card-complete`), el más fácil de aserverar sin
    // ambigüedad tras recargar.
    const terrainRadio = page.getByRole("radio", { name: "Trocha" });
    await expect(terrainRadio).toBeVisible({ timeout: NAV_TIMEOUT });
    await terrainRadio.click();
    await page.getByRole("radio", { name: "4 — Técnico" }).click();
    await page.getByRole("checkbox", { name: "Rock garden" }).click();
    // Acotado al sheet: `RaceConditionsCard` (mismo tab desde la 045) también
    // expone un `aria-label` «Sin registro de notas» que casaría con "Notas".
    await page
      .getByRole("dialog")
      .getByLabel("Notas", { exact: true })
      .fill(
        "Tramo con raíces cerca de la meta; avisar en la charla técnica previa.",
      );

    await page.getByRole("button", { name: "Guardar" }).click();
    await expect(page.getByText(/guardada correctamente/i)).toBeVisible({
      timeout: NAV_TIMEOUT,
    });

    // Recarga — re-consultar el DOM, no confiar en estado en memoria (mismo
    // criterio que E2E-043-001 de la parte 1).
    await page.reload();
    await expect(courseTab).toBeVisible({ timeout: NAV_TIMEOUT });

    // Tarjeta editable del coach — 4/4 campos llenos.
    const editCard = page.getByTestId("course-description-card-complete");
    await expect(editCard).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(editCard).toContainText("Trocha");
    await expect(editCard).toContainText("4 — Técnico");
    await expect(editCard).toContainText("Rock garden");
    await expect(editCard).toContainText(
      "Tramo con raíces cerca de la meta; avisar en la charla técnica previa.",
    );

    // La pestaña del coach monta `CourseSummary` en modo `mapOnly`: la
    // descripción solo vive en la tarjeta editable, sin recap duplicado.
    await expect(
      page.getByTestId("course-summary-description"),
    ).toHaveCount(0);
  });

  test("E2E-043-003: la tabla de resultados muestra Distancia/Vel. prom. cuando la válida tiene circuito configurado", async ({
    page,
  }) => {
    await loginAsCoach(page);
    const token = await getToken(page);

    const found = await discoverCompletedEventWithResults(page, token);
    test.skip(
      found == null,
      "No hay ninguna válida completada CON resultados importados en este " +
        "entorno — sin al menos una fila de resultado real no hay ninguna " +
        "sección de categoría que renderizar (`ResultsTable` filtra " +
        "`cat.rows.length > 0`), así que esta aserción no se puede " +
        "ejercitar. Mismo tipo de gap de datos que el documentado para " +
        "'vueltas por categoría' en el encabezado de la parte 1 de este " +
        "archivo.",
    );
    const { eventId, categoryId } = found!;

    await ensureCourseSetupForResultsColumns(page, token, eventId, categoryId);

    await page.goto(`/competitions/${eventId}?tab=results`);
    const categorySection = page.getByTestId(
      `results-category-section-${categoryId}`,
    );
    await expect(categorySection).toBeVisible({ timeout: COLD_START_TIMEOUT });
    await expect(
      categorySection.getByRole("columnheader", { name: "Distancia" }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(
      categorySection.getByRole("columnheader", { name: "Vel. prom." }),
    ).toBeVisible();

    // Recarga — confirma que las columnas dependen de `has_course_data`
    // persistido, no de estado en memoria de esta sesión.
    await page.reload();
    await expect(
      categorySection.getByRole("columnheader", { name: "Distancia" }),
    ).toBeVisible({ timeout: NAV_TIMEOUT });
  });

  // NOTA (limpieza de convocatoria): E2E-043-004 ("un padre ve la tarjeta
  // vía convocatoria") se eliminó — la visibilidad ya no admite un camino
  // sin resultado. Queda pendiente un E2E positivo (padre SÍ ve la tarjeta)
  // seedeado con un `RaceResult` real; esta suite no tiene un helper liviano
  // para crear uno por API (los resultados solo entran por el Import
  // Wizard/PDF), así que ese caso queda sin cubrir por ahora.
  test("E2E-043-005: un padre NO ve tarjeta de circuito ni error en una válida donde su hijo/a no está registrado", async ({
    page,
    browser,
  }) => {
    await loginAsCoach(page);
    const coachToken = await getToken(page);

    const seriesId = await createCupSeries(page, coachToken);
    const raceEventId = await createRaceEvent(page, coachToken, seriesId);
    // Circuito SÍ configurado — así la ausencia de tarjeta se debe a la
    // falta de vínculo del padre con esta válida, no a que la válida esté
    // vacía de datos (de lo contrario la aserción sería trivial).
    await uploadCourseVariantApi(
      page,
      coachToken,
      raceEventId,
      "Circuito completo",
      COURSE_REDUCED_GPX,
    );
    // A propósito: NINGÚN atleta del padre se convoca ni tiene resultado en
    // esta válida — mantiene la premisa "válida NO registrada para este
    // padre" (`course-api.md` §1: 404 `course_not_available` sin ningún
    // atleta propio en la nómina ni en los resultados de esta válida).

    const parentContext = await browser.newContext();
    try {
      const parentPage = await parentContext.newPage();
      await loginAsParent(parentPage);
      await parentPage.goto(`/parents/competitions/${raceEventId}`);

      await expect(parentPage.getByTestId("parent-results-page")).toBeVisible(
        { timeout: COLD_START_TIMEOUT },
      );

      // Sin tarjeta de reconocimiento...
      await expect(parentPage.getByTestId("course-summary")).toHaveCount(0);
      // ...y sin ningún rastro de un error o toast relacionado con el
      // circuito (404 `course_not_available` se trata como "ausente", nunca
      // como error — a diferencia de un fallo real de
      // `resultsQuery`/`standingsQuery`, que sí puede mostrar su propio
      // banner de error, pero esa es una superficie totalmente distinta y
      // no es lo que esta aserción cubre).
      // El nombre de la propia válida de prueba («E2E Circuito — válida de
      // prueba …», ver `createRaceEvent`) es el encabezado de la página y
      // contiene la palabra: se excluye para que la aserción mida solo el
      // contenido del perfil de circuito, no el título del evento.
      await expect(
        parentPage.getByText(/circuito/i).filter({ hasNotText: /E2E Circuito/ }),
      ).toHaveCount(0);
    } finally {
      await parentContext.close();
    }
  });
});
