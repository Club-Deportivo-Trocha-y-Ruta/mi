// Requiere: docker compose up (backend real en :8000 + MySQL) contra un
// stack DEDICADO de e2e con datos sintéticos — ver la nota de estado abajo.
//
// Feature 040 (growth module redesign), US4 — vista de familia del tab
// "Crecimiento" (T064). Sigue el mismo patrón de login real que
// `growth.spec.ts` (T044/T054, lado coach) y `parents.spec.ts` (E2E-PAD-*):
// credenciales sembradas por `backend/scripts/seed.py`, sin inventar
// usuarios ni tokens falsos — a diferencia de `ai-insights-parent.spec.ts`,
// que mockea toda la red porque su propósito es la frontera RBAC
// coach/padre, no el flujo real de login.
//
// Contrato: `specs/040-growth-module-redesign/contracts/growth-tab-ui.md`
// (composición modo padre) + `contracts/band-vocabulary.md` (vocabulario
// familiar, sin etiquetas clínicas). Historia de usuario 4 (spec.md):
// "Confirm the classification shown corresponds to the latest measurement,
// no numeric Z/percentile appears anywhere on the page, no clinical
// headline label appears, the bibliography section is absent, and the AI
// explanation is read-only."
//
// Estado de ejecución (2026-09-04): NO se ejecutó contra el stack docker
// local de este entorno. `specs/040-growth-module-redesign/checklists/coach-tab.md`
// (gate de Fase 5, firmado por engineering-lead) ya documentó, para el
// equivalente de esta spec en T054, dos razones que aplican igual aquí y
// que esta tarea no puede resolver por sí sola:
//   (a) el seed de `backend/scripts/seed.py` sólo corre si `clubs` está
//       vacío — este volumen de MySQL ya tiene datos, así que el login
//       real (`padre@trochayruta.com` / `Parent2026!`) puede devolver 401
//       aunque `GET /health` responda 200 (confirmado con curl directo);
//   (b) privacidad: esa misma base de datos local contiene datos reales,
//       no de demostración, y Playwright escribe capturas/trazas/videos en
//       cada fallo — correr esta spec ahí arriesgaría con capturar datos
//       reales de un menor, violando Ley 1581 aun sin tocar el código.
// Verificado en su lugar con `npx playwright test --list` (sintaxis e
// imports válidos, ver reporte de la tarea) y con la suite vitest existente
// (`GrowthTab.parent.test.tsx`, `FamilyStageCard.test.tsx`,
// `FamilyBandCards.test.tsx`), que cubren en jsdom cada aserción de este
// archivo con datos 100% sintéticos. Pendiente de ejecución real en el
// stack dedicado de e2e que `checklists/coach-tab.md` deja a cargo de
// `devops-engineer`, en la puerta de Fase 7 (T072), junto con T044/T054.
import { test, expect, type Page } from '@playwright/test';

const PARENT_EMAIL = 'padre@trochayruta.com';
const PARENT_PASSWORD = 'Parent2026!';

// ---------------------------------------------------------------------------
// Helpers — mismo idioma que growth.spec.ts / parents.spec.ts
// ---------------------------------------------------------------------------

async function loginAsParent(page: Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(PARENT_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(PARENT_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/**
 * Abre el detalle del único hijo vinculado a `padre@trochayruta.com` en el
 * seed ("Santiago" — atleta ficticio del fixture, no un dato real; ver
 * `backend/scripts/seed.py`). El link "Ver detalle de <nombre>" es el mismo
 * que usa `parents.spec.ts` (E2E-PAD-003) — se evita el link de "próxima
 * sesión" con `.first()` + el nombre exacto, mismo criterio.
 */
async function openChildDetail(page: Page) {
  await expect(page).toHaveURL(/\/my-athletes/);
  const anthroResponse = page.waitForResponse(
    (r) => /\/anthropometry/.test(r.url()) && r.status() === 200,
    { timeout: 30_000 },
  );
  await page
    .getByRole('link', { name: /ver detalle de santiago/i })
    .first()
    .click();
  await expect(page).toHaveURL(/\/my-athletes\/\d+/);
  await anthroResponse;
}

/**
 * Selecciona el tab "Crecimiento" del lado padre. El botón sólo se
 * renderiza cuando `records.length > 0` (mismo guard que
 * `AthleteDetailPage.tsx`, `contracts/growth-tab-ui.md`) — no depende de
 * auto-selección de tab (retirada en la Fase 7 de esta misma feature).
 */
async function openGrowthTab(page: Page) {
  const growthTabButton = page.getByRole('button', { name: /^Crecimiento$/i });
  await expect(growthTabButton).toBeVisible({ timeout: 15_000 });
  // El resumen (`growth-summary`) ya lo pidió la página al cargar, porque las
  // tarjetas superiores (T070) leen de él; el tab reutiliza la caché de
  // TanStack Query y no dispara una segunda petición. Se espera al contenido
  // real del tab en vez de a una respuesta de red.
  await growthTabButton.click();
  await expect(page.getByTestId('growth-tab')).toBeVisible();
  await expect(page.getByTestId('family-stage-card')).toBeVisible({ timeout: 20_000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test('E2E-040-003: vista de familia — tarjetas de la medición más reciente, sin numerales ni bibliografía', async ({
  page,
}) => {
  await loginAsParent(page);
  await openChildDetail(page);
  await openGrowthTab(page);

  const tab = page.getByTestId('growth-tab');

  // --- Tarjetas familiares: etapa + bandas, siempre de la medición más
  //     reciente (FR-017) — ambas se alimentan de `useGrowthSummary`, que ya
  //     resuelve del lado servidor cuál es el último registro. ------------
  const stageCard = page.getByTestId('family-stage-card');
  await expect(stageCard).toBeVisible();
  await expect(stageCard.getByText('Etapa de desarrollo', { exact: true })).toBeVisible();

  const bandCards = page.getByTestId('family-band-cards');
  await expect(bandCards).toBeVisible();
  await expect(page.getByTestId('family-band-card-height')).toBeVisible();
  await expect(page.getByTestId('family-band-card-bmi')).toBeVisible();
  await expect(bandCards.getByText('Estatura para su edad', { exact: true })).toBeVisible();
  await expect(bandCards.getByText('Peso para su estatura', { exact: true })).toBeVisible();

  // --- Sin numerales clínicos en toda la vista (FR-016/FR-017, SC-004):
  //     ni Z-score, ni percentil, ni el offset de maduración. -------------
  const tabText = (await tab.innerText()).trim();
  expect(tabText).not.toMatch(/Z\s*=/);
  expect(tabText).not.toMatch(/P\d{1,3}\b/);
  expect(tabText).not.toMatch(/offset/i);

  // --- Sin etiquetas clínicas de cabecera (band-vocabulary.md: la familia
  //     nunca ve la etiqueta de coach, sólo la narrativa). ----------------
  expect(tabText).not.toMatch(/\bObesidad\b/);
  expect(tabText).not.toMatch(/\bDelgadez\b/);
  expect(tabText).not.toMatch(/\bTalla baja\b/);

  // --- Sin bibliografía (exclusiva del coach, contracts/growth-tab-ui.md
  //     §Component tree: `ResearchReferences` no se monta en modo padre). -
  await expect(page.getByText(/Fuentes bibliográficas/i)).toHaveCount(0);

  // --- Sin controles exclusivos de coach en la curva simplificada
  //     (eje Cronológica/Biológica, "Detalle") — FR-015/FR-016. ----------
  await expect(page.getByRole('radio', { name: 'Cronológica' })).toHaveCount(0);
  await expect(page.getByRole('radio', { name: 'Biológica' })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Detalle' })).toHaveCount(0);
});

test('E2E-040-004: vista de familia — la tarjeta de IA es de solo lectura, sin botón de generar', async ({
  page,
}) => {
  await loginAsParent(page);
  await openChildDetail(page);
  await openGrowthTab(page);

  // `PHVExplanationCard readOnly` sólo instancia la query GET (caché) y
  // termina en uno de dos estados terminales: contenido cacheado
  // (`phv-explanation-readonly`) o mensaje pasivo de espera
  // (`phv-explanation-idle`) — nunca el flujo de generación del coach.
  const readOnlyCard = page.getByTestId('phv-explanation-readonly');
  const idleCard = page.getByTestId('phv-explanation-idle');
  await expect(readOnlyCard.or(idleCard)).toBeVisible({ timeout: 20_000 });

  // Ni "Generar explicación" ni "Regenerar" existen del lado padre — esos
  // son acciones exclusivas de `PHVExplanationCoach`.
  await expect(page.getByRole('button', { name: /Generar/i })).toHaveCount(0);
  await expect(page.getByRole('button', { name: /Regenerar/i })).toHaveCount(0);
});
