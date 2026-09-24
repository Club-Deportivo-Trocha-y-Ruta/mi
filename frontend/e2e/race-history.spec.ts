/**
 * E2E spec — feature 044 (race history backfill), T087.
 *
 * ✅ ESTADO DE EJECUCIÓN (2026-09-22): corrida por primera vez y en VERDE
 * contra la pila aislada real (`docker-compose.e2e.yml`, `frontend/scripts/
 * e2e-stack.sh up`, backend :8001 / MySQL :3307 / seed de desarrollo) —
 * `1 passed (6.9s)`. La primera versión de este archivo (escrita sin
 * Docker disponible) tenía cuatro bugs reales que sólo salieron al
 * ejecutarla de verdad, documentados en el código donde se corrigieron:
 * (1) un commit exitoso navega fuera del wizard de inmediato
 * (`CompetitionImportPage.tsx::handleCompleted`) — nunca deja ver
 * `import-wizard-step3`; (2) el botón de confirmar puede pintarse
 * habilitado antes de que `matchesData` esté listo, y `submitCommit` hace
 * no-op silencioso si se clickea en ese instante; (3) un click de
 * Playwright basado en coordenadas (incluido `force: true`) puede aterrizar
 * sobre un toast sonner que cubre el botón en vez del botón mismo — hubo
 * que usar `.evaluate(el => el.click())` (DOM nativo) en los botones de
 * acción del wizard, la revisión de identidad y el tablero; (4) la sesión
 * vive en `sessionStorage`, no en cookies — `clearCookies()` no cierra
 * sesión. Cada corrección quedó comentada en su sitio, no solo aquí.
 *
 * Requiere re-ejecutarse contra una pila con MySQL recién creada (volumen
 * limpio): el commit es idempotente por SHA256 (`race_import`) y una
 * segunda corrida contra la MISMA base ya sembrada responde "ya fue
 * commiteado" en el paso 1 — visto de primera mano al iterar sobre esta
 * spec. `frontend/scripts/e2e-stack.sh down -v && … up` entre corridas.
 *
 * Cubre `tasks.md` T087: stage de dos archivos sintéticos (dos temporadas
 * de Copa Valle) → corregir/reconocer un hueco de completitud → decidir
 * identidad → commit → el coach ve la serie con marcador de cambio de
 * categoría en el tab «Carreras» (vista «Progresión») → la vista de familia
 * no expone ningún nombre de tercero. Ver `specs/044-race-history-backfill/quickstart.md`
 * §4/§6/§7 (este spec es literalmente el `npm run test:e2e -- race-history.spec.ts`
 * que ahí se documenta) y `contracts/identity-review-api.md` /
 * `contracts/historical-load.md` / `contracts/ui-history.md`.
 *
 * Confirmado en la corrida real: el commit del wizard
 * (`wizard-step2-confirm`) intenta comprometer la válida directamente
 * (nada que decidir para la primera válida, 2024 — navega derecho a
 * resultados); si hay candidatos de identidad pendientes (la segunda,
 * 2025), responde `409 identity_pending` (cuerpo PLANO desde la feature
 * 045: `{detail, pending_for_import, review_path}`) y el wizard pinta el
 * mensaje `wizard-identity-gate-message` + el link
 * `wizard-identity-review-link` hacia «Cargas e identidades»; el tablero
 * `/competitions/imports?seccion=cargas` (antes `/competitions/history`) es
 * lo que hace falta para el commit FINAL una vez decidida la identidad.
 *
 * Feature 045 (T064): las tres pantallas viejas (`/competitions/history`,
 * `/competitions/identity-review`, `/competitions/unlinked`) ahora son
 * redirecciones a `/competitions/imports?seccion=cargas|identidades|sin-enlazar`
 * y el tab «Carreras» del atleta reúne progresión, análisis y comparador
 * (`?tab=races&view=progresion|analisis|comparar`); el spec usa las rutas
 * canónicas nuevas y ya no busca `history-progression-card` sino
 * `progression-view`.
 *
 * Sintéticos: los dos PDFs se generan en tiempo de test con
 * `results_pdf_builder.py` (nunca los archivos reales de
 * `backend/tests/fixtures/race/`). Nombres/clubes/ciudades ficticios —
 * "Mateo Ejemplar (Ficticio)" y "Sofia Demostrativa" no son personas
 * reales. El atleta del club usado para enlazar (Santiago) y su padre
 * (`padre@trochayruta.com`) son los del seed de desarrollo
 * (`backend/scripts/seed.py`), mismos datos sintéticos que
 * `growth-parent.spec.ts` / `parents.spec.ts`.
 */
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { test, expect, type Page } from "@playwright/test";

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const PARENT = { email: "padre@trochayruta.com", password: "Parent2026!" };

// Misma convención que `frontend/e2e/helpers/demo-athlete.ts` /
// `helpers/session.ts` — E2E_API_BASE_URL apunta a la pila aislada
// (docker-compose.e2e.yml, backend en :8001) cuando está seteada.
function apiBaseUrl(): string {
  return process.env.E2E_API_BASE_URL ?? "http://localhost:8000";
}

const BACKEND = apiBaseUrl();
const COLD_START_TIMEOUT = 90_000;
const NAV_TIMEOUT = 30_000;

const REPO_ROOT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
  "..",
);
const BACKEND_DIR = path.join(REPO_ROOT, "backend");

// ---------------------------------------------------------------------------
// Generación de los dos PDFs sintéticos — puente hacia
// `results_pdf_builder.py` (Python/WeasyPrint), ver el docstring del script.
// ---------------------------------------------------------------------------

function generateFixturePdfs(): { file2024: string; file2025: string } {
  const outDir = fs.mkdtempSync(
    path.join(os.tmpdir(), "e2e-race-history-"),
  );
  const python = process.env.E2E_PYTHON ?? path.join(BACKEND_DIR, ".venv", "bin", "python");
  const stdout = execFileSync(
    python,
    ["scripts/generate_e2e_race_history_fixtures.py", outDir],
    {
      cwd: BACKEND_DIR,
      env: {
        ...process.env,
        // Mismo requisito que correr pytest en local (macOS/Homebrew) —
        // ver docs/technical-notes.md y el docstring del script.
        DYLD_FALLBACK_LIBRARY_PATH:
          process.env.DYLD_FALLBACK_LIBRARY_PATH ?? "/opt/homebrew/lib",
      },
      encoding: "utf-8",
    },
  );
  const [file2024, file2025] = stdout.trim().split("\n");
  if (!file2024 || !file2025 || !fs.existsSync(file2024) || !fs.existsSync(file2025)) {
    throw new Error(
      `generateFixturePdfs: salida inesperada del generador:\n${stdout}`,
    );
  }
  return { file2024, file2025 };
}

// ---------------------------------------------------------------------------
// Login — mismo patrón que race-course.spec.ts / prefill-import-from-competition.spec.ts
// ---------------------------------------------------------------------------

async function login(
  page: Page,
  creds: { email: string; password: string },
): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(creds.email);
  await page.getByRole("textbox", { name: /contraseña/i }).fill(creds.password);
  await page.getByRole("button", { name: /ingresar|iniciar sesión/i }).click();
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

async function apiGet(page: Page, token: string, urlPath: string): Promise<unknown> {
  return page.evaluate(
    async ({ backend, t, p }) => {
      const res = await fetch(`${backend}${p}`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      if (!res.ok) throw new Error(`apiGet ${p}: HTTP ${res.status}`);
      return res.json();
    },
    { backend: BACKEND, t: token, p: urlPath },
  );
}

async function apiPost(
  page: Page,
  token: string,
  urlPath: string,
  body: unknown,
): Promise<{ ok: boolean; status: number; body: unknown }> {
  return page.evaluate(
    async ({ backend, t, p, b }) => {
      const res = await fetch(`${backend}${p}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${t}`,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(b),
      });
      const json = await res.json().catch(() => null);
      return { ok: res.ok, status: res.status, body: json };
    },
    { backend: BACKEND, t: token, p: urlPath, b: body },
  );
}

// ---------------------------------------------------------------------------
// Wizard — sube un archivo, llena metadata, resuelve el hueco de
// completitud (si aparece) y comprometa la válida.
// ---------------------------------------------------------------------------

interface StageOptions {
  filePath: string;
  seriesName: string;
  seasonYear: number;
  validaNum: number;
  eventName: string;
  eventDate: string; // yyyy-mm-dd
  location: string;
  categoryHeader: string;
  /** true si esta categoría trae un hueco de completitud a reconocer. */
  expectGap: boolean;
}

/**
 * Sube+llena el wizard hasta intentar el commit (step2 → confirm).
 *
 * CORREGIDO tras la primera corrida real contra la pila aislada
 * (2026-09-22): un commit exitoso NUNCA deja ver `import-wizard-step3` en
 * esta ruta — `CompetitionImportPage.tsx::handleCompleted` navega de
 * inmediato (`replace: true`) a `/competitions/{id}?tab=results` en cuanto
 * `submitCommit` resuelve, así que el estado de éxito interno del wizard
 * nunca llega a pintarse. `import-wizard-step3` sólo es observable en el
 * camino de ERROR (p. ej. `identity_pending`), porque ahí
 * `onCompleted` nunca se llama y no hay navegación. Devuelve cuál de los
 * dos pasó.
 */
async function stageAndAttemptCommit(
  page: Page,
  opts: StageOptions,
): Promise<"navigated" | "step3-error"> {
  await page.goto("/competitions/import");
  await expect(page.getByTestId("import-wizard-step1")).toBeVisible({
    timeout: NAV_TIMEOUT,
  });

  await page.getByTestId("wizard-series-kind").selectOption("cup");
  await page.getByTestId("wizard-series-name").fill(opts.seriesName);
  await page.getByTestId("wizard-season").fill(String(opts.seasonYear));
  await page.getByTestId("wizard-valida-num").fill(String(opts.validaNum));
  await page.getByTestId("wizard-event-name").fill(opts.eventName);
  await page.getByTestId("wizard-event-date").fill(opts.eventDate);
  await page.getByTestId("wizard-location").fill(opts.location);
  await page
    .getByTestId("race-upload-resultados-input")
    .setInputFiles(opts.filePath);

  // `{ force: true }`: un toast sonner ajeno a este flujo (p. ej.
  // "Condiciones sin registrar") puede aparecer justo encima del botón y
  // bloquear el click real — no es parte de lo que este spec verifica.
  await page.getByTestId("wizard-step1-submit").click({ force: true });
  await expect(page.getByTestId("import-wizard-step2")).toBeVisible({
    timeout: NAV_TIMEOUT,
  });
  await expect(page.getByTestId("wizard-dry-run-loading")).toHaveCount(0, {
    timeout: NAV_TIMEOUT,
  });

  if (opts.expectGap) {
    const ackButton = page.getByTestId(`acknowledge-${opts.categoryHeader}`);
    await expect(ackButton).toBeVisible({ timeout: NAV_TIMEOUT });
    await ackButton.click();
    await expect(page.getByTestId("acknowledge-gap-dialog")).toBeVisible();
    await page.getByTestId("ag-reason-select").click();
    // Primer motivo del catálogo cerrado (`GET /imports/acknowledge-reasons`)
    // — el contenido exacto no importa para este spec, sólo que exista uno.
    await page.getByRole("option").first().click();
    await page.getByRole("button", { name: /reconocer/i }).click();
    await expect(page.getByTestId("acknowledge-gap-dialog")).toHaveCount(0);
  }

  // `canCommit` en ImportWizard.tsx depende de `matchesData` (una query
  // aparte de la que llena `CategoryMappingTable`) — un click apenas el
  // botón se pinta puede caer en el guard `if (!matchesData) return;` de
  // `submitCommit` y quedarse pegado en step 2 sin error ni navegación
  // (encontrado en la corrida real 2026-09-22). Esperar a `toBeEnabled`
  // antes del click evita ese no-op silencioso.
  const confirmButton = page.getByTestId("wizard-step2-confirm");
  await expect(confirmButton).toBeEnabled({ timeout: NAV_TIMEOUT });
  // `.click({ force: true })` de Playwright sigue siendo un click basado en
  // coordenadas — si un toast sonner ajeno cubre exactamente esas
  // coordenadas, `force` se limita a saltar el chequeo de "obstruido" pero
  // el evento real puede seguir aterrizando en el toast, no en el botón
  // (encontrado en la corrida real 2026-09-22: el click no producía ni
  // error ni cambio de estado). `.evaluate(el => el.click())` dispara un
  // click de DOM nativo directo sobre el nodo, sin pasar por coordenadas.
  await confirmButton.evaluate((el) => (el as HTMLButtonElement).click());
  await expect
    .poll(
      async () => {
        if (/\/competitions\/\d+(?:$|\?)/.test(page.url())) return "navigated";
        if (await page.getByTestId("import-wizard-step3").isVisible().catch(() => false)) {
          return "step3-error";
        }
        return "pending";
      },
      { timeout: NAV_TIMEOUT },
    )
    .not.toBe("pending");

  return /\/competitions\/\d+(?:$|\?)/.test(page.url()) ? "navigated" : "step3-error";
}

/** true si el step3 quedó en el estado de error "identidad pendiente". */
async function isIdentityPendingError(page: Page): Promise<boolean> {
  const errorBox = page.getByTestId("wizard-step3-error");
  if ((await errorBox.count()) === 0) return false;
  return (await page.getByTestId("wizard-identity-review-link").count()) > 0;
}

// ---------------------------------------------------------------------------
// Revisión de identidad — decide cada candidato pendiente por nombre.
// ---------------------------------------------------------------------------

async function decideAllPendingCandidates(page: Page): Promise<void> {
  // Feature 045: «¿Es la misma persona?» vive en «Cargas e identidades»
  // (`/competitions/identity-review` ahora solo redirige aquí).
  await page.goto("/competitions/imports?seccion=identidades");
  await expect(page.getByTestId("review-progress")).toBeVisible({
    timeout: NAV_TIMEOUT,
  });

  // Cola "un candidato a la vez": mientras quede al menos un pendiente,
  // `candidate-left`/`candidate-right` muestran el siguiente.
  for (let guard = 0; guard < 10; guard++) {
    const progress = (await page.getByTestId("review-progress").textContent()) ?? "";
    if (/sin candidatos por revisar/i.test(progress)) break;
    const match = progress.match(/(\d+) de (\d+) decididos/i);
    if (match && match[1] === match[2]) break;

    const left = page.getByTestId("candidate-left");
    if ((await left.count()) === 0) break;
    const leftText = (await left.textContent()) ?? "";

    if (/mateo/i.test(leftText)) {
      // "Mateo Ejemplar Ficticio" / "Mateo Ejemplar" — mismo corredor, un
      // apellido de menos impreso en 2025 (same_person_suspect).
      await page.getByTestId("decide-same-person").evaluate((el) => (el as HTMLButtonElement).click());
    } else {
      // "Sofia Demostrativa" en dos clubes/ciudades distintos
      // (homonym_suspect vía club_and_city_differ) — dos personas.
      await page.getByTestId("decide-different-people").evaluate((el) => (el as HTMLButtonElement).click());
    }
    // Espera a que la cola avance (el siguiente candidato reemplaza al
    // actual, o desaparece si ya no queda ninguno). `left.textContent()`
    // sobre un nodo que ya no existe se queda esperando su propio timeout
    // interno (encontrado en la corrida real 2026-09-22, al decidir el
    // ÚLTIMO candidato) — `count()` primero no espera de la misma forma.
    await expect
      .poll(
        async () => {
          if ((await left.count()) === 0) return "gone";
          return (await left.textContent().catch(() => null)) ?? "gone";
        },
        { timeout: NAV_TIMEOUT },
      )
      .not.toBe(leftText);
  }

  const finalProgress = (await page.getByTestId("review-progress").textContent()) ?? "";
  expect(finalProgress).toMatch(/sin candidatos por revisar|^(\d+) de \1 decididos/i);
}

// ---------------------------------------------------------------------------
// Sección «Cargas» de «Cargas e identidades» — commit final de una válida
// ya lista (antes el tablero «Carga histórica» de `/competitions/history`).
// ---------------------------------------------------------------------------

async function commitFromBoard(page: Page, validaLabelPattern: RegExp): Promise<void> {
  await page.goto("/competitions/imports?seccion=cargas");
  const row = page
    .locator('[data-testid^="import-row-"]')
    .filter({ hasText: validaLabelPattern });
  await expect(row).toBeVisible({ timeout: NAV_TIMEOUT });

  const testId = await row.getAttribute("data-testid");
  const id = testId?.replace("import-row-", "");
  if (!id) throw new Error(`commitFromBoard: no se pudo leer el id de la fila ${testId}`);

  const commitBtn = page.getByTestId(`commit-${id}`);
  const commitPendingBtn = page.getByTestId(`commit-pending-${id}`);
  if (await commitBtn.count()) {
    await commitBtn.evaluate((el) => (el as HTMLButtonElement).click());
  } else if (await commitPendingBtn.count()) {
    await commitPendingBtn.evaluate((el) => (el as HTMLButtonElement).click());
  } else {
    throw new Error("commitFromBoard: ni commit ni commit-pending disponibles todavía");
  }

  await expect(row.getByText(/cargado/i)).toBeVisible({ timeout: NAV_TIMEOUT });
}

// ---------------------------------------------------------------------------
// Test
// ---------------------------------------------------------------------------

test.describe("Feature 044 — historial Copa Valle (T087)", () => {
  test("stage dos temporadas → hueco → identidad → commit → Carreras (coach) → sin terceros (familia)", async ({
    page,
  }) => {
    const { file2024, file2025 } = generateFixturePdfs();

    await login(page, COACH);
    const coachToken = await getToken(page);

    const seriesName = `E2E Historico Copa Valle ${Date.now()}`;

    // 1) Válida 2024 — archivo limpio, sin hueco. Primera aparición de
    //    "Mateo"/"Sofia": nada que comparar todavía, así que el commit
    //    debería resolverse directo (ver el SUPUESTO del encabezado).
    const outcome2024 = await stageAndAttemptCommit(page, {
      filePath: file2024,
      seriesName,
      seasonYear: 2024,
      validaNum: 3,
      eventName: "E2E Válida 2024",
      eventDate: "2024-06-15",
      location: "Sede E2E Ficticia",
      categoryHeader: "INFANTIL A",
      expectGap: false,
    });
    if (outcome2024 === "step3-error" && (await isIdentityPendingError(page))) {
      await decideAllPendingCandidates(page);
      await commitFromBoard(page, /E2E Válida 2024|Válida 3/i);
    } else {
      // "navigated": CompetitionImportPage ya nos llevó a
      // /competitions/{id}?tab=results — el commit de la primera válida
      // (nada con qué comparar todavía) se resolvió directo.
      expect(outcome2024).toBe("navigated");
    }

    // 1b) Enlazar el "Mateo" de 2024 al atleta del club sembrado por el seed
    //     de desarrollo ("Santiago", el mismo que usa growth-parent.spec.ts /
    //     parents.spec.ts) ANTES de cargar 2025. La cola de identidad solo
    //     levanta candidatos si un lado del par ya es un atleta del club
    //     (`identity_review.in_club_scope`, decisión 2026-09-22 de la 044):
    //     sin este enlace previo el commit de 2025 no tiene nada que revisar,
    //     no dispara el candado por carga de la 045 y el "Mateo" de 2025
    //     queda como otro competidor (sin serie cross-temporada).
    const unlinked = (await apiGet(
      page,
      coachToken,
      "/api/race-competitors/?unlinked=true",
    )) as { items?: Array<{ id: number; normalized_name: string }> } | Array<{ id: number; normalized_name: string }>;
    const competitors = Array.isArray(unlinked) ? unlinked : unlinked.items ?? [];
    const mateo = competitors.find((c) => /mateo ejemplar/i.test(c.normalized_name));
    expect(mateo, "competitor 'Mateo Ejemplar' sin enlazar, tras el commit de 2024").toBeTruthy();

    const athletes = (await apiGet(page, coachToken, "/api/athletes")) as
      | Array<{ id: number; first_name?: string }>
      | { items: Array<{ id: number; first_name?: string }> };
    const athleteList = Array.isArray(athletes) ? athletes : athletes.items;
    const santiago = athleteList.find((a) => /santiago/i.test(a.first_name ?? ""));
    test.skip(!santiago, "Seed sin atleta 'Santiago' (padre@trochayruta.com) — no se puede verificar el tab Carreras");
    if (!santiago || !mateo) return;

    const linkResult = await apiPost(
      page,
      coachToken,
      `/api/race-competitors/${mateo.id}/link`,
      { athlete_id: santiago.id },
    );
    expect(linkResult.ok, `link competitor->athlete: ${JSON.stringify(linkResult.body)}`).toBeTruthy();

    // 2) Válida 2025 — mismo "Mateo" con un apellido de menos, misma
    //    "Sofia" con club/ciudad distintos, y el hueco de completitud en
    //    INFANTIL B (puesto 3 ausente) que hay que reconocer antes de
    //    poder continuar.
    const outcome2025 = await stageAndAttemptCommit(page, {
      filePath: file2025,
      seriesName,
      seasonYear: 2025,
      validaNum: 4,
      eventName: "E2E Válida 2025",
      eventDate: "2025-06-21",
      location: "Sede E2E Ficticia",
      categoryHeader: "INFANTIL B",
      expectGap: true,
    });

    // 3) Identidad: casi seguro bloqueada aquí (Mateo/Sofia ya tienen con
    //    qué compararse). Si por algún motivo no lo estuvo, el helper de
    //    abajo simplemente no encuentra candidatos pendientes y sigue.
    if (outcome2025 === "step3-error" && (await isIdentityPendingError(page))) {
      // Feature 045: el bloqueo es por carga y trae el copy de
      // `contracts/ui-copy.md` con el conteo de ESTA carga, más un enlace a
      // `review_path` (conserva `import=<id>` para «Volver a la carga»).
      await expect(page.getByTestId("wizard-identity-gate-message")).toContainText(
        /decisi(ón|ones) de identidad pendientes? para esta carga/i,
      );
      await expect(page.getByTestId("wizard-identity-review-link")).toHaveAttribute(
        "href",
        /\/competitions\/imports\?seccion=identidades&import=\d+/,
      );
      await decideAllPendingCandidates(page);
      // 4) Commit final de la segunda válida desde el tablero.
      await commitFromBoard(page, /E2E Válida 2025|Válida 4/i);
    } else {
      // Con el "Mateo" de 2024 ya enlazado a un atleta del club (paso 1b) el
      // candado por carga de la 045 DEBE frenar el commit de 2025: llegar aquí
      // significa que no lo hizo.
      throw new Error(
        `commit de 2025 sin 409 identity_pending pese a tener un lado enlazado a un atleta del club (resultado: ${outcome2025})`,
      );
    }

    // 6) Vista coach — tab «Carreras» del atleta (vista «Progresión», la
    //    predeterminada desde la feature 045): la progresión histórica y el
    //    marcador de cambio de categoría (INFANTIL A → INFANTIL B).
    await page.goto(`/athletes/${santiago.id}?tab=races&view=progresion`);
    await expect(page.getByTestId("progression-view")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(page.getByTestId("history-category-changes")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    // Privacidad estructural: ningún nombre de tercero (el homónimo
    // "Sofia Demostrativa" ni el corredor genérico) en la vista del coach.
    await expect(page.getByText(/sofia demostrativa/i)).toHaveCount(0);

    // 7) Vista de familia — mismo tab, cero nombres de terceros, sin
    //    importar si la política de fecha de registro recorta el
    //    histórico visible (eso es US7, no el foco de este spec).
    //
    // La app guarda la sesión en `sessionStorage` (ver `login()`/`getToken()`
    // arriba), no en cookies — `clearCookies()` no cierra la sesión del
    // coach, así que `/login` redirige de inmediato a `/dashboard` y el
    // textbox de correo nunca aparece (encontrado en la corrida real
    // 2026-09-22). Limpiar `sessionStorage` es lo que de verdad cierra la
    // sesión.
    await page.evaluate(() => sessionStorage.clear());
    await login(page, PARENT);
    await expect(page).toHaveURL(/\/my-athletes/, { timeout: NAV_TIMEOUT });
    await page
      .getByRole("link", { name: /ver detalle de santiago/i })
      .first()
      .click();
    await expect(page).toHaveURL(/\/my-athletes\/\d+/, { timeout: NAV_TIMEOUT });
    await page.getByTestId("parent-tab-races").click();
    // Esperar a que «Progresión» pinte antes de las aserciones de ausencia
    // (si no, `toHaveCount(0)` pasaría trivialmente sobre un tab vacío).
    await expect(page.getByTestId("progression-view")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    // La familia no ve «Comparar» (solo coach) ni las brechas vs. 1.ª
    // posición / podio.
    await expect(page.getByTestId("carreras-view-comparar")).toHaveCount(0);
    await expect(page.getByText(/brecha vs\. 1\.ª posición|brecha vs\. podio/i)).toHaveCount(0);
    await expect(page.getByText(/sofia demostrativa/i)).toHaveCount(0);
    await expect(page.getByText(/mateo ejemplar ficticio/i)).toHaveCount(0);
  });
});
