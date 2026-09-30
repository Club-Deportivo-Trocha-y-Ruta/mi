// E2E — Jornada de medición grupal (feature 048, T054).
//
// Requiere el stack e2e AISLADO (frontend/scripts/e2e-stack.sh). Datos
// sintéticos; nunca el stack "me".
//
// Cubre:
//  - Selección de 3 → medir 1 → omitir 1 → medir 1 → conteos del resumen.
//  - Salida a pliegues de un deportista elegible → «Volver a la jornada»
//    retoma la cola; recargar a mitad de jornada la pierde (por diseño) y la
//    selección muestra «Medido hoy» para el ya guardado.
//  - Variante 360 px: selección + una captura, sin scroll horizontal.
//
// Cada prueba crea sus propios deportistas «Ficticio» (el roster muestra a
// todo el club, así que se seleccionan por nombre exacto) y los limpia.
import { test, expect, type Page } from '@playwright/test';

import { loginAsCoach } from './helpers/demo-athlete';
import {
  cleanupAthlete,
  createSyntheticAthlete,
  listRecords,
  localIso,
  uniqueSuffix,
  type SyntheticAthlete,
} from './helpers/anthropometry-fixtures';

async function createGroup(page: Page, count: number, tag: string): Promise<SyntheticAthlete[]> {
  const group = `${tag}${uniqueSuffix()}`;
  const athletes: SyntheticAthlete[] = [];
  for (let i = 0; i < count; i += 1) {
    athletes.push(await createSyntheticAthlete(page.request, { tag: `${group}N${i}` }));
  }
  return athletes;
}

async function openPickerAndStart(page: Page, athletes: SyntheticAthlete[]) {
  await page.goto('/athletes');
  await page.getByRole('link', { name: 'Jornada de medición' }).click();
  await expect(page).toHaveURL(/\/anthropometry\/session$/);
  await expect(page.getByRole('heading', { name: 'Jornada de medición', level: 1 })).toBeVisible();
  for (const athlete of athletes) {
    await page.getByRole('checkbox', { name: athlete.fullName, exact: true }).click();
  }
  await page.getByRole('button', { name: `Empezar jornada (${athletes.length})` }).click();
}

function currentAthleteHeading(page: Page) {
  return page.locator('#session-current-athlete');
}

/** Captura rápida con la fecha bloqueada de la jornada; deja el panel «Revisar» abierto. */
async function quickFillAndReview(page: Page) {
  const quick = page.getByRole('radio', { name: 'Rápido' });
  if ((await quick.getAttribute('aria-checked')) !== 'true') await quick.click();
  const form = page.getByRole('form', { name: 'Captura rápida de medición' });
  await expect(form).toBeVisible();
  await expect(form.getByLabel('Fecha de la medición')).toBeDisabled();
  await expect(form.getByLabel('Fecha de la medición')).toHaveValue(localIso());
  await form.getByLabel(/^peso \(kg\)$/i).fill('41');
  await form.getByLabel(/^talla de pie \(cm\)$/i).fill('151');
  await form.getByLabel(/lectura del tallímetro, sentado \(cm\)/i).fill('76');
  await form.getByRole('button', { name: 'Revisar y guardar' }).click();
  await expect(page.getByRole('heading', { name: 'Revisar', exact: true })).toBeVisible();
}

async function expectNoHorizontalScroll(page: Page, width: number) {
  const scrollWidth = await page.evaluate(() => document.documentElement.scrollWidth);
  expect(scrollWidth, 'sin scroll horizontal de página').toBeLessThanOrEqual(width);
}

test.describe('Jornada de medición (048)', () => {
  test('selecciona 3, mide 1, omite 1, mide 1 y el resumen cuenta bien', async ({ page }) => {
    const athletes = await createGroup(page, 3, 'Cola');
    try {
      await loginAsCoach(page);
      await openPickerAndStart(page, athletes);

      await expect(page.getByText('1 de 3', { exact: true })).toBeVisible({ timeout: 15_000 });
      const first = (await currentAthleteHeading(page).innerText()).trim();
      await quickFillAndReview(page);
      await page.getByRole('button', { name: 'Guardar y terminar' }).click();
      await expect(page.getByRole('status').filter({ hasText: `Guardado: ${first}.` })).toBeVisible({
        timeout: 15_000,
      });

      await expect(page.getByText('2 de 3', { exact: true })).toBeVisible();
      const second = (await currentAthleteHeading(page).innerText()).trim();
      expect(second).not.toBe(first);
      await page.getByRole('button', { name: 'Omitir por hoy' }).click();

      await expect(page.getByText('3 de 3', { exact: true })).toBeVisible();
      const third = (await currentAthleteHeading(page).innerText()).trim();
      await quickFillAndReview(page);
      await page.getByRole('button', { name: 'Guardar y terminar' }).click();

      await expect(page.getByRole('heading', { name: 'Resumen de la jornada' })).toBeVisible({
        timeout: 15_000,
      });
      await expect(page.getByRole('heading', { name: 'Medidos (2)' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Omitidos (1)' })).toBeVisible();
      await expect(page.getByRole('heading', { name: 'Pendientes (0)' })).toBeVisible();
      await expect(page.getByRole('link', { name: first })).toBeVisible();
      await expect(page.getByRole('link', { name: third })).toBeVisible();
      await expect(page.getByRole('button', { name: `Medir ahora a ${second}` })).toBeVisible();

      // Exactamente una medición por medido, ninguna para el omitido.
      const counts = await Promise.all(
        athletes.map(async (a) => ({ name: a.fullName, n: (await listRecords(page.request, a.id)).length })),
      );
      expect(counts.find((c) => c.name === first)?.n).toBe(1);
      expect(counts.find((c) => c.name === second)?.n).toBe(0);
      expect(counts.find((c) => c.name === third)?.n).toBe(1);

      await page.getByRole('button', { name: 'Terminar jornada' }).click();
      await expect(page.getByRole('button', { name: /empezar jornada/i })).toBeVisible();
    } finally {
      for (const a of athletes) await cleanupAthlete(page.request, a.id);
    }
  });

  test('desvío a pliegues vuelve a la cola; recargar pierde la jornada y marca «Medido hoy»', async ({
    page,
  }) => {
    const athletes = await createGroup(page, 2, 'Pliegues');
    try {
      await loginAsCoach(page);
      await openPickerAndStart(page, athletes);

      await expect(page.getByText('1 de 2', { exact: true })).toBeVisible({ timeout: 15_000 });
      const first = (await currentAthleteHeading(page).innerText()).trim();
      await quickFillAndReview(page);
      // Deportista sintético de ~12 años sin pliegues previos: elegible.
      const skinfoldsExit = page.getByRole('button', { name: 'Guardar y agregar pliegues' });
      await expect(skinfoldsExit).toBeVisible({ timeout: 15_000 });
      await skinfoldsExit.click();

      await expect(page).toHaveURL(
        /\/athletes\/\d+\/anthropometry\/\d+\/skinfolds\?returnTo=\/anthropometry\/session$/,
        { timeout: 15_000 },
      );
      await expect(page.getByTestId('skinfold-wizard')).toBeVisible();
      await page.getByRole('link', { name: 'Volver a la jornada' }).click();

      await expect(page).toHaveURL(/\/anthropometry\/session$/);
      await expect(page.getByText('2 de 2', { exact: true })).toBeVisible();
      const second = (await currentAthleteHeading(page).innerText()).trim();
      expect(second).not.toBe(first);

      // Recargar a mitad de jornada: la cola vive solo en memoria.
      await page.reload();
      await expect(page.getByRole('button', { name: /empezar jornada \(0\)/i })).toBeVisible({
        timeout: 15_000,
      });
      const firstCard = page.getByRole('listitem').filter({
        has: page.getByRole('checkbox', { name: first, exact: true }),
      });
      const secondCard = page.getByRole('listitem').filter({
        has: page.getByRole('checkbox', { name: second, exact: true }),
      });
      await expect(firstCard.getByText('Medido hoy')).toBeVisible();
      await expect(secondCard.getByText('Medido hoy')).toHaveCount(0);
    } finally {
      for (const a of athletes) await cleanupAthlete(page.request, a.id);
    }
  });
});

test.describe('Jornada de medición (048) — teléfono 360 px', () => {
  test.use({ viewport: { width: 360, height: 780 }, hasTouch: true });

  test('selección y una captura sin scroll horizontal', async ({ page }) => {
    const athletes = await createGroup(page, 1, 'Movil');
    try {
      await loginAsCoach(page);
      await page.goto('/anthropometry/session');
      await expect(page.getByRole('heading', { name: 'Jornada de medición', level: 1 })).toBeVisible({
        timeout: 15_000,
      });
      await page.getByRole('checkbox', { name: athletes[0].fullName, exact: true }).click();
      await expectNoHorizontalScroll(page, 360);
      await page.getByRole('button', { name: 'Empezar jornada (1)' }).click();

      await expect(page.getByText('1 de 1', { exact: true })).toBeVisible({ timeout: 15_000 });
      await expectNoHorizontalScroll(page, 360);
      await quickFillAndReview(page);
      await expectNoHorizontalScroll(page, 360);
      await page.getByRole('button', { name: 'Guardar y terminar' }).click();

      await expect(page.getByRole('heading', { name: 'Medidos (1)' })).toBeVisible({
        timeout: 15_000,
      });
      await expectNoHorizontalScroll(page, 360);
      expect(await listRecords(page.request, athletes[0].id)).toHaveLength(1);
    } finally {
      for (const a of athletes) await cleanupAthlete(page.request, a.id);
    }
  });
});
