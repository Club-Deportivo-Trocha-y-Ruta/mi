// E2E — Captura antropométrica guiada (feature 048, T052).
//
// Requiere el stack e2e AISLADO (frontend/scripts/e2e-stack.sh: backend :8001,
// MySQL :3307, datos sintéticos). Nunca el stack "me".
//
// Cubre:
//  - Camino guiado: Preparación → 4 pasos → banco 40 → talla neta visible →
//    peso +20 % vs la anterior → advertencia en «Revisar» → etiqueta de
//    maduración en lenguaje llano → guardar → la fila existe en el historial.
//  - Modo «Rápido» persistido tras recargar.
//  - Segunda captura en la misma fecha → diálogo «Ya existe una medición…».
//  - Bloqueo sin conexión: POST abortado → aviso → «Reintentar» → exactamente
//    una fila nueva.
//  - Variante 360 px táctil del camino guiado: sin scroll horizontal e
//    ilustración encima del campo.
//
// Datos: cada prueba crea su propio deportista «Ficticio» por API (los specs
// corren en paralelo y la regla «una medición por fecha» los haría chocar) y
// lo limpia al final (mediciones borradas + deportista archivado).
import { test, expect, type Page } from '@playwright/test';

import { loginAsCoach } from './helpers/demo-athlete';
import {
  cleanupAthlete,
  createRecord,
  createSyntheticAthlete,
  daysAgoIso,
  listRecords,
  localIso,
  toDisplayDate,
  type SyntheticAthlete,
} from './helpers/anthropometry-fixtures';

const created: number[] = [];

test.afterEach(async ({ request }) => {
  while (created.length > 0) {
    const id = created.pop() as number;
    await cleanupAthlete(request, id);
  }
});

async function newAthlete(page: Page, tag: string): Promise<SyntheticAthlete> {
  const athlete = await createSyntheticAthlete(page.request, { tag });
  created.push(athlete.id);
  return athlete;
}

/** Medición previa (hace 120 días) para que la plausibilidad tenga contra qué comparar. */
async function seedPreviousRecord(page: Page, athleteId: number) {
  await createRecord(page.request, athleteId, {
    evaluation_date: daysAgoIso(120),
    weight_kg: 40,
    standing_height_cm: 150,
    sitting_height_cm: 75.5,
    arm_span_cm: 151,
  });
}

async function openCaptureFromProfile(page: Page, athleteId: number) {
  await page.goto(`/athletes/${athleteId}?tab=anthropometry`);
  await page.getByRole('link', { name: /\+ nueva medición/i }).click();
  await expect(page).toHaveURL(new RegExp(`/athletes/${athleteId}/anthropometry/new$`));
  await expect(page.getByRole('heading', { name: 'Nueva medición', level: 1 })).toBeVisible({
    timeout: 15_000,
  });
}

async function expectNoHorizontalScroll(page: Page, width: number) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth, 'sin scroll horizontal de página').toBeLessThanOrEqual(width);
}

/**
 * Recorre el asistente guiado completo hasta «Revisar». Con `phoneWidth`
 * comprueba en cada paso que no haya scroll horizontal y que la ilustración
 * quede encima del campo.
 */
async function walkGuidedPath(page: Page, phoneWidth?: number) {
  await expect(page.getByRole('heading', { name: 'Preparación' })).toBeVisible();
  if (phoneWidth) await expectNoHorizontalScroll(page, phoneWidth);
  await page.getByRole('button', { name: 'Empezar' }).click();

  const steps: Array<{ heading: string; label: RegExp; value: string }> = [
    { heading: 'Peso', label: /^peso \(kg\)$/i, value: '48' },
    { heading: 'Talla de pie', label: /^talla de pie \(cm\)$/i, value: '152' },
  ];
  for (const step of steps) {
    await expect(page.getByRole('heading', { name: step.heading, exact: true })).toBeVisible();
    const input = page.getByLabel(step.label);
    if (phoneWidth) {
      await expectNoHorizontalScroll(page, phoneWidth);
      const img = page.locator('form img').first();
      const imgBox = await img.boundingBox();
      const inputBox = await input.boundingBox();
      expect(imgBox, 'la ilustración se renderiza').not.toBeNull();
      expect(inputBox).not.toBeNull();
      // Teléfono: ilustración ARRIBA del campo (una columna).
      expect((imgBox as { y: number; height: number }).y + (imgBox as { height: number }).height)
        .toBeLessThanOrEqual((inputBox as { y: number }).y);
    }
    await input.fill(step.value);
    await page.getByRole('button', { name: 'Siguiente' }).click();
  }

  // Talla sentado con banco de 40 cm: lectura 116 → neta 76,0 cm.
  await expect(page.getByRole('heading', { name: 'Talla sentado', exact: true })).toBeVisible();
  await page.getByLabel(/lectura en el tallímetro \(cm\)/i).fill('116');
  await page.getByLabel(/altura del banco \(cm\)/i).fill('40');
  await expect(page.getByTestId('net-sitting-height')).toContainText('76,0 cm');
  if (phoneWidth) await expectNoHorizontalScroll(page, phoneWidth);
  await page.getByRole('button', { name: 'Siguiente' }).click();

  await expect(page.getByRole('heading', { name: 'Envergadura', exact: true })).toBeVisible();
  await page.getByLabel(/^envergadura \(cm\)$/i).fill('153');
  await page.getByRole('button', { name: 'Siguiente' }).click();

  await expect(page.getByRole('heading', { name: 'Revisar', exact: true })).toBeVisible();
}

async function assertReviewAndSave(page: Page, athleteId: number) {
  // Peso 48 vs 40 anterior (+20 %) → advertencia ámbar, no bloqueante.
  const warnings = page.getByRole('list', { name: 'Advertencias de la medición' });
  await expect(warnings).toBeVisible({ timeout: 15_000 });
  await expect(warnings).toContainText(/el peso cambió más de un 10 %/i);
  // Maduración en lenguaje llano (niño de ~12 años, offset < −1 → pre-estirón).
  await expect(page.getByTestId('phv-plain-summary')).toContainText('Aún no llega al estirón');

  await page.getByRole('button', { name: 'Guardar y terminar' }).click();
  await expect(page).toHaveURL(new RegExp(`/athletes/${athleteId}\\?tab=anthropometry`), {
    timeout: 15_000,
  });
}

test.describe('Captura antropométrica (048) — escritorio', () => {
  test('camino guiado: banco, advertencia de peso, maduración en llano y fila en el historial', async ({
    page,
  }) => {
    const athlete = await newAthlete(page, 'Guiado');
    await seedPreviousRecord(page, athlete.id);
    await loginAsCoach(page);
    await openCaptureFromProfile(page, athlete.id);

    await walkGuidedPath(page);
    // Desde `sm` los valores van en tabla: talla sentado NETA y detalle del banco.
    const values = page.getByTestId('capture-review-values-table');
    await expect(values).toContainText('76,0 cm');
    await expect(values).toContainText(/lectura 116,0 cm − banco 40,0 cm/i);
    await assertReviewAndSave(page, athlete.id);

    const history = page.getByTestId('anthropometry-history-desktop');
    const todayRow = history.getByRole('row').filter({ hasText: toDisplayDate(localIso()) });
    await expect(todayRow).toHaveCount(1, { timeout: 15_000 });
    // La fila guardada lleva el marcador «Revisar» (aviso de peso).
    await expect(todayRow.getByTestId('history-plausibility-badge')).toBeVisible();

    const records = await listRecords(page.request, athlete.id);
    const saved = records.find((r) => r.evaluation_date.slice(0, 10) === localIso());
    expect(saved, 'la medición de hoy existe').toBeTruthy();
    // Se envió la talla NETA (116 − 40), nunca la lectura bruta.
    expect(Number(saved?.sitting_height_cm)).toBe(76);
  });

  test('el modo «Rápido» se conserva al recargar la página', async ({ page }) => {
    const athlete = await newAthlete(page, 'Rapido');
    await loginAsCoach(page);
    await openCaptureFromProfile(page, athlete.id);

    const quickToggle = page.getByRole('radio', { name: 'Rápido' });
    await quickToggle.click();
    await expect(page.getByRole('form', { name: 'Captura rápida de medición' })).toBeVisible();

    await page.reload();
    await expect(page.getByRole('form', { name: 'Captura rápida de medición' })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole('radio', { name: 'Rápido' })).toHaveAttribute('aria-checked', 'true');
    await expect(page.getByRole('heading', { name: 'Preparación' })).toHaveCount(0);
  });

  test('una segunda captura en la misma fecha abre el diálogo y «Cambiar la fecha» enfoca la fecha', async ({
    page,
  }) => {
    const athlete = await newAthlete(page, 'MismaFecha');
    await createRecord(page.request, athlete.id, {
      evaluation_date: localIso(),
      weight_kg: 42,
      standing_height_cm: 152,
      sitting_height_cm: 76,
    });
    await loginAsCoach(page);
    await openCaptureFromProfile(page, athlete.id);

    await page.getByRole('radio', { name: 'Rápido' }).click();
    await page.getByLabel(/^peso \(kg\)$/i).fill('42.5');
    await page.getByLabel(/^talla de pie \(cm\)$/i).fill('152.5');
    await page.getByLabel(/lectura del tallímetro, sentado \(cm\)/i).fill('76.5');
    await page.getByRole('button', { name: 'Revisar y guardar' }).click();
    await page.getByRole('button', { name: 'Guardar y terminar' }).click();

    const dialog = page.getByRole('alertdialog', { name: /ya existe una medición de esta fecha/i });
    await expect(dialog).toBeVisible({ timeout: 15_000 });
    await expect(dialog.getByRole('button', { name: 'Abrir la existente' })).toBeVisible();
    await dialog.getByRole('button', { name: 'Cambiar la fecha' }).click();
    await expect(dialog).toBeHidden();
    await expect(page.getByLabel('Fecha de la medición')).toBeFocused();

    // No se creó un segundo registro.
    expect(await listRecords(page.request, athlete.id)).toHaveLength(1);
  });

  test('sin conexión al guardar: aviso, los valores quedan y «Reintentar» crea exactamente una fila', async ({
    page,
  }) => {
    const athlete = await newAthlete(page, 'SinRed');
    await loginAsCoach(page);
    await openCaptureFromProfile(page, athlete.id);

    await page.getByRole('radio', { name: 'Rápido' }).click();
    await page.getByLabel(/^peso \(kg\)$/i).fill('41');
    await page.getByLabel(/^talla de pie \(cm\)$/i).fill('151');
    await page.getByLabel(/lectura del tallímetro, sentado \(cm\)/i).fill('76');
    await page.getByRole('button', { name: 'Revisar y guardar' }).click();
    await expect(page.getByRole('heading', { name: 'Revisar', exact: true })).toBeVisible();

    // Solo el POST de creación (no el dry-run de plausibilidad) falla por red.
    const createPath = `/api/athletes/${athlete.id}/anthropometry`;
    const isCreate = (url: URL) => url.pathname === createPath;
    let aborted = 0;
    await page.route(isCreate, async (route) => {
      if (route.request().method() === 'POST') {
        aborted += 1;
        await route.abort('internetdisconnected');
        return;
      }
      await route.fallback();
    });

    await page.getByRole('button', { name: 'Guardar y terminar' }).click();
    const banner = page.getByRole('alert').filter({ hasText: /sin conexión — no se guardó/i });
    await expect(banner).toBeVisible({ timeout: 15_000 });
    expect(aborted).toBe(1);
    // Los valores siguen en pantalla (sin borrador local).
    await expect(page.getByLabel(/^peso \(kg\)$/i)).toHaveValue('41');

    await page.unroute(isCreate);
    await banner.getByRole('button', { name: 'Reintentar' }).click();
    await expect(page).toHaveURL(new RegExp(`/athletes/${athlete.id}\\?tab=anthropometry`), {
      timeout: 15_000,
    });

    const records = await listRecords(page.request, athlete.id);
    expect(records, 'exactamente una fila nueva').toHaveLength(1);
    await expect(
      page
        .getByTestId('anthropometry-history-desktop')
        .getByRole('row')
        .filter({ hasText: toDisplayDate(localIso()) }),
    ).toHaveCount(1);
  });
});

test.describe('Captura antropométrica (048) — teléfono 360 px', () => {
  test.use({ viewport: { width: 360, height: 780 }, hasTouch: true });

  test('camino guiado sin scroll horizontal, ilustración encima del campo', async ({ page }) => {
    const athlete = await newAthlete(page, 'Movil');
    await seedPreviousRecord(page, athlete.id);
    await loginAsCoach(page);
    await openCaptureFromProfile(page, athlete.id);

    await walkGuidedPath(page, 360);
    // En teléfono los valores van en lista de definición, no en tabla.
    await expect(page.getByTestId('capture-review-values-list')).toBeVisible();
    await expect(page.getByTestId('capture-review-values-table')).toBeHidden();
    await expectNoHorizontalScroll(page, 360);
    await assertReviewAndSave(page, athlete.id);

    await expect(
      page.getByTestId('anthropometry-history').getByTestId('record-date').filter({
        hasText: toDisplayDate(localIso()),
      }),
    ).toHaveCount(1, { timeout: 15_000 });
    await expectNoHorizontalScroll(page, 360);
  });
});
