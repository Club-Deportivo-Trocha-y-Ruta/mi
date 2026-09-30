// Requiere el stack e2e aislado (frontend/scripts/e2e-stack.sh).
//
// Feature 048 (T055): «+ Nueva medición» ya no abre un formulario en línea
// con vista previa PHV en vivo; es un enlace a la página de captura
// (`/athletes/:id/anthropometry/new`) y el PHV se muestra en el paso
// «Revisar» (resumen en lenguaje llano + «Detalle técnico» plegado).
//
// Cada prueba usa su propio deportista sintético («Ficticio») y lo limpia:
// con la regla «una medición por fecha» (409), medir siempre al atleta del
// seed en la misma fecha hacía el spec no repetible sobre el mismo stack.
import { test, expect, type Page } from '@playwright/test';

import { loginAsCoach } from './helpers/demo-athlete';
import {
  cleanupAthlete,
  createSyntheticAthlete,
  listRecords,
  toDisplayDate,
  type SyntheticAthlete,
} from './helpers/anthropometry-fixtures';

const EVAL_DATE = '2026-04-14';

async function openCapture(page: Page, athlete: SyntheticAthlete) {
  await page.goto(`/athletes/${athlete.id}`);
  // Pestaña «Antropometría» (con acento).
  await page.getByRole('button', { name: /antropometr[ií]a/i }).click();
  // «+ Nueva medición» es ahora un enlace a la página de captura.
  await page.getByRole('link', { name: /nueva medici[óo]n/i }).click();
  await expect(page).toHaveURL(new RegExp(`/athletes/${athlete.id}/anthropometry/new$`));
}

async function fillQuick(
  page: Page,
  values: { weight: string; standing: string; sitting: string; date?: string },
) {
  await page.getByRole('radio', { name: 'Rápido' }).click();
  // Sin `date`, queda la fecha de hoy que propone el formulario.
  if (values.date) await page.getByLabel('Fecha de la medición').fill(values.date);
  await page.getByLabel(/^peso \(kg\)$/i).fill(values.weight);
  await page.getByLabel(/^talla de pie \(cm\)$/i).fill(values.standing);
  await page.getByLabel(/lectura del tallímetro, sentado \(cm\)/i).fill(values.sitting);
  await page.getByRole('button', { name: 'Revisar y guardar' }).click();
}

// E2E-005 — Registrar medición antropométrica y ver PHV calculado
test('E2E-005: registrar medición antropométrica y verificar cálculo PHV', async ({ page }) => {
  const athlete = await createSyntheticAthlete(page.request, { tag: 'E005' });
  try {
    await loginAsCoach(page);
    await openCapture(page, athlete);
    await fillQuick(page, { weight: '45.5', standing: '155.0', sitting: '73.0', date: EVAL_DATE });

    // Resumen de maduración en «Revisar»: etiqueta llana + detalle técnico.
    const summary = page.getByTestId('phv-plain-summary');
    await expect(summary).toBeVisible();
    await expect(summary).toContainText(
      /aún no llega al estirón|está en pleno estirón|ya pasó el estirón/i,
    );
    await summary.getByRole('button', { name: 'Detalle técnico' }).click();
    // Longitud de pierna = 155 − 73 = 82 cm.
    await expect(summary).toContainText('82 cm');
    await expect(summary).toContainText('Maturity offset');
    await expect(summary).toContainText('Edad al PHV');

    await page.getByRole('button', { name: 'Guardar y terminar' }).click();

    // El historial (escritorio, 1280 px) muestra la nueva medición.
    await expect(page).toHaveURL(new RegExp(`/athletes/${athlete.id}\\?tab=anthropometry`), {
      timeout: 15_000,
    });
    const history = page.getByTestId('anthropometry-history-desktop');
    await expect(history).toBeVisible({ timeout: 15_000 });
    await expect(history.getByRole('row').filter({ hasText: toDisplayDate(EVAL_DATE) })).toHaveCount(1);
    expect(await listRecords(page.request, athlete.id)).toHaveLength(1);
  } finally {
    await cleanupAthlete(page.request, athlete.id);
  }
});

// E2E-006 — El PHV de «Revisar» se recalcula al corregir un valor
test('E2E-006: el resumen PHV se recalcula al corregir la talla sentado', async ({ page }) => {
  const athlete = await createSyntheticAthlete(page.request, { tag: 'E006' });
  try {
    await loginAsCoach(page);
    await openCapture(page, athlete);

    // Hoy, niño nacido el 2014-05-10 (≥ 12,3 años), 152 cm: sentado 76 →
    // offset ≈ −1,8 (antes del estirón); sentado 85 → ≈ −0,85 (en pleno estirón).
    await fillQuick(page, { weight: '42', standing: '152', sitting: '76' });
    const summary = page.getByTestId('phv-plain-summary');
    await expect(summary).toContainText('Aún no llega al estirón');

    // Editar un valor invalida el panel «Revisar»; al volver a revisar, el
    // resumen refleja el nuevo cálculo (sentado 85 → en pleno estirón).
    await page.getByLabel(/lectura del tallímetro, sentado \(cm\)/i).fill('85');
    await expect(page.getByRole('heading', { name: 'Revisar', exact: true })).toHaveCount(0);
    await page.getByRole('button', { name: 'Revisar y guardar' }).click();
    await expect(summary).toContainText('Está en pleno estirón');
    // Nada se guardó: «Revisar» es previo al guardado.
    expect(await listRecords(page.request, athlete.id)).toHaveLength(0);
  } finally {
    await cleanupAthlete(page.request, athlete.id);
  }
});
