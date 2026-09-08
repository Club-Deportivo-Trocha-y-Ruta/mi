// Requiere: docker compose up (backend real en :8000 + MySQL).
//
// Feature 040 (growth module redesign), US2 — tab "Crecimiento" decision
// first del coach. Parte 1 (T044): tiles de resumen + reglas de
// entrenamiento. Parte 2 (T054, Fase 5/US3) suma el toolbar de la curva
// (indicador/eje/tabla/export) al mismo archivo.
import { test, expect } from '@playwright/test';
import { gotoDemoAthlete } from './helpers/demo-athlete';

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';

// Viewport de tableta apaisada (SC-002): los cinco indicadores del bloque
// resumen deben verse sin hacer scroll a esta resolución.
// SC-002 habla de una tableta de 1024 px de ancho; se toma la orientación
// vertical del iPad Pro (1024×1366). En horizontal (1024×768) la cabecera de
// la página (tarjeta del atleta + tarjetas T070 + acudientes + barra de tabs
// en dos filas) ocupa ~610 px, así que la fila de estado queda parcialmente
// bajo el pliegue y la tarjeta de próxima medición a ~900 px: hace falta un
// scroll corto. Medido el 2026-09-05 en el stack e2e aislado.
test.use({ viewport: { width: 1024, height: 1366 } });

async function loginAsCoach(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function navigateToFirstAthlete(page: import('@playwright/test').Page) {
  // Atleta demo resuelto por API (con mediciones sembradas): el orden de la
  // tabla cambia cuando `athletes.spec.ts` crea atletas en paralelo.
  await gotoDemoAthlete(page);
}

// El primer atleta de la lista sembrada tiene mediciones registradas — el
// botón "Crecimiento" sólo se renderiza cuando `records.length > 0`
// (contracts/growth-tab-ui.md). No dependemos de la auto-selección de tab
// de la página (se retira en la Fase 7 de esta misma feature) — la
// seleccionamos explícitamente, igual que `history.spec.ts` (E2E-008).
async function openGrowthTab(page: import('@playwright/test').Page) {
  const growthTabButton = page.getByRole('button', { name: /^Crecimiento$/i });
  await expect(growthTabButton).toBeVisible({ timeout: 15_000 });
  await growthTabButton.click();
  await expect(page).toHaveURL(/\/athletes\/\d+\?tab=growth/);
  await expect(page.getByTestId('growth-tab')).toBeVisible();
}

test('E2E-040-001: tab Crecimiento — los cinco indicadores del resumen se ven sin scroll y "Ver todas las reglas" expande', async ({
  page,
}) => {
  await loginAsCoach(page);
  await navigateToFirstAthlete(page);
  await openGrowthTab(page);

  // Bloque resumen real (useGrowthSummary) — esperar a que resuelva antes de
  // medir el viewport, no al skeleton de carga del chunk lazy.
  await expect(page.getByTestId('growth-status-row')).toBeVisible({ timeout: 15_000 });
  await expect(page.getByTestId('growth-next-measurement')).toBeVisible();

  // Las cinco lecturas del contrato (`GrowthStatusRow` × 4 + `NextMeasurementCard`)
  // deben caber en el viewport inicial de 1024×1366 sin hacer scroll —
  // SC-002 (revisado en tablet/phone por T045; aquí sólo la vista tablet).
  // Las etiquetas se buscan dentro de la fila de estado: las tarjetas
  // superiores de la página (T070) repiten "Etapa" fuera del tab.
  const statusRow = page.getByTestId('growth-status-row');
  const readings = [
    statusRow.getByText('Etapa', { exact: true }),
    statusRow.getByText('Velocidad de talla', { exact: true }),
    statusRow.getByText('Talla para la edad', { exact: true }),
    statusRow.getByText('IMC para la edad', { exact: true }),
    page.getByTestId('growth-next-measurement'),
  ];
  for (const reading of readings) {
    await expect(reading).toBeVisible();
    await expect(reading).toBeInViewport();
  }

  // "Qué cambia en el entrenamiento" — expandir el detalle completo de reglas.
  const rulesSection = page.getByTestId('growth-rules');
  await expect(rulesSection).toBeVisible();
  const rulesToggle = rulesSection.getByRole('button', { name: /ver todas las reglas/i });
  await expect(rulesToggle).toBeVisible();
  await expect(rulesToggle).toHaveAttribute('aria-expanded', 'false');

  await rulesToggle.click();
  await expect(rulesToggle).toHaveAttribute('aria-expanded', 'true');
  // El detalle completo trae las nueve reglas con su estado (Permitido /
  // Con cuidado / No permitido) — basta con verificar que al menos una
  // insignia de estado quedó visible tras expandir.
  await expect(
    rulesSection.getByText(/Permitido|Con cuidado|No permitido/i).first(),
  ).toBeVisible();
});

// T054 (Fase 5/US3) — toolbar de la curva: indicador, eje biológico, vista
// Tabla y exportación PNG, per `contracts/growth-tab-ui.md` §Toolbar. El eje
// Biológica sólo se ofrece mientras el indicador activo no sea IMC
// (`GrowthCurveSection::showAxisToggle`), así que se alterna primero con
// "Talla" y luego se cambia a "IMC" — no al revés.
test('E2E-040-002: curva de crecimiento — indicador, eje biológico, tabla y exportación PNG', async ({
  page,
}) => {
  await loginAsCoach(page);
  await navigateToFirstAthlete(page);
  await openGrowthTab(page);

  const curveSection = page.getByTestId('growth-curve');
  await expect(curveSection).toBeVisible({ timeout: 15_000 });

  const toolbar = page.getByTestId('growth-curve-toolbar');
  await expect(toolbar).toBeVisible();

  // Estado inicial: indicador "Talla", eje "Cronológica".
  await expect(toolbar.getByRole('radio', { name: 'Talla' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  const axisChrono = toolbar.getByRole('radio', { name: 'Cronológica' });
  const axisBio = toolbar.getByRole('radio', { name: 'Biológica' });
  await expect(axisBio).toBeVisible();
  await expect(axisChrono).toHaveAttribute('aria-checked', 'true');

  // 1. Alternar a eje Biológica — el rótulo del eje X de la gráfica cambia
  // ("Edad" → "Edad relativa al PHV", `PercentileChart.tsx`).
  await axisBio.click();
  await expect(axisBio).toHaveAttribute('aria-checked', 'true');
  await expect(curveSection.getByText('Edad relativa al PHV')).toBeVisible();

  // 2. Cambiar indicador Talla → IMC — el toggle de eje deja de ofrecerse
  // (no aplica a IMC, `contracts/growth-tab-ui.md` §Props).
  await toolbar.getByRole('radio', { name: 'IMC' }).click();
  await expect(toolbar.getByRole('radio', { name: 'IMC' })).toHaveAttribute(
    'aria-checked',
    'true',
  );
  await expect(toolbar.getByRole('radio', { name: 'Biológica' })).not.toBeVisible();

  // 3. Vista Tabla — la fila más reciente debe coincidir (percentil y banda)
  // con el tile "IMC para la edad" del bloque resumen: ambos leen el mismo
  // valor almacenado del registro más reciente (`useGrowthMetrics` /
  // `useGrowthSummary`).
  await toolbar.getByRole('radio', { name: 'Tabla' }).click();
  const table = page.getByTestId('growth-curve-table');
  await expect(table).toBeVisible();

  const firstRow = table.locator('tbody tr').first();
  await expect(firstRow).toBeVisible();
  const rowPercentileText = (await firstRow.locator('td').nth(4).innerText()).trim();
  const rowBandText = (await firstRow.locator('td').nth(5).innerText()).trim();
  const rowPercentileMatch = rowPercentileText.match(/P(\d+)/);
  expect(rowPercentileMatch, `celda de percentil inesperada: "${rowPercentileText}"`).not.toBeNull();

  const imcTile = page
    .getByTestId('growth-status-row')
    .locator('div.shadow-card', { hasText: 'IMC para la edad' });
  await expect(imcTile).toBeVisible();
  const tileText = await imcTile.innerText();
  const tilePercentileMatch = tileText.match(/P(\d+)/);
  expect(tilePercentileMatch, `tile de IMC sin percentil: "${tileText}"`).not.toBeNull();

  expect(rowPercentileMatch![1]).toBe(tilePercentileMatch![1]);
  expect(tileText).toContain(rowBandText);

  // 4. Volver a vista Gráfica — el botón "Descargar PNG" sólo existe ahí
  // (`GrowthCurveSection`: `onExport={view === "chart" ? handleExportPng : undefined}`)
  // — y descargar la curva: el nombre de archivo sigue el patrón existente
  // (`crecimiento-<indicador>-<timestamp>.png`, sin nombre del atleta — Ley 1581).
  await toolbar.getByRole('radio', { name: 'Gráfica' }).click();
  const exportButton = page.getByTestId('export-png-button');
  await expect(exportButton).toBeVisible();

  const downloadPromise = page.waitForEvent('download');
  await exportButton.click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^crecimiento-.*\.png$/);
});
