// E2E — Editar y eliminar mediciones antropométricas (feature 048, T053).
//
// Requiere el stack e2e AISLADO (frontend/scripts/e2e-stack.sh). Datos
// sintéticos; nunca el stack "me".
//
// Cubre:
//  - El coach edita la talla sentado de una medición suya (la etapa PHV de la
//    fila cambia) y la elimina con el diálogo de confirmación.
//  - `coach2` no ve «Editar»/«Eliminar» en una medición de `coach` y un `PUT`
//    directo devuelve 403 `not_record_author`.
//  - La familia no ve acciones ni el marcador «Revisar», y el payload que
//    recibe no trae `can_modify` ni `plausibility_flags`.
import { test, expect, type Page } from '@playwright/test';

import { COACH2_EMAIL, COACH2_PASSWORD, loginAsCoach } from './helpers/demo-athlete';
import {
  apiBaseUrl,
  authHeaders,
  cleanupAthlete,
  createRecord,
  createSyntheticAthlete,
  daysAgoIso,
  listRecords,
  toDisplayDate,
  type ApiRecord,
} from './helpers/anthropometry-fixtures';

const PARENT_EMAIL = 'padre@trochayruta.com';
const PARENT_PASSWORD = 'Parent2026!';
// Atleta 1 del seed: el único vinculado al padre demo.
const PARENT_CHILD_ID = 1;

function historyRow(page: Page, isoDate: string) {
  return page
    .getByTestId('anthropometry-history-desktop')
    .getByRole('row')
    .filter({ hasText: toDisplayDate(isoDate) });
}

test.describe('Editar / eliminar mediciones (048)', () => {
  test('el coach edita la talla sentado (cambia la etapa PHV) y luego elimina la medición', async ({
    page,
  }) => {
    const athlete = await createSyntheticAthlete(page.request, { tag: 'Editar' });
    try {
      const date = daysAgoIso(30);
      // Niño ~12 años, 152 cm: sentado 76 → Pre-PHV; sentado 85 → Circa-PHV.
      await createRecord(page.request, athlete.id, {
        evaluation_date: date,
        weight_kg: 42,
        standing_height_cm: 152,
        sitting_height_cm: 76,
      });

      await loginAsCoach(page);
      await page.goto(`/athletes/${athlete.id}?tab=anthropometry`);
      const row = historyRow(page, date);
      await expect(row).toHaveCount(1, { timeout: 15_000 });
      await expect(row).toContainText('Pre-PHV');

      await row.getByRole('link', { name: `Editar la medición del ${toDisplayDate(date)}` }).click();
      await expect(page.getByRole('heading', { name: 'Editar medición', level: 1 })).toBeVisible({
        timeout: 15_000,
      });
      const sitting = page.getByLabel(/lectura del tallímetro, sentado \(cm\)/i);
      // En edición se muestra la talla NETA con banco 0.
      await expect(sitting).toHaveValue('76');
      await sitting.fill('85');
      await page.getByRole('button', { name: 'Revisar y guardar' }).click();
      await expect(page.getByTestId('phv-plain-summary')).toContainText('Está en pleno estirón');
      await page.getByRole('button', { name: 'Guardar cambios' }).click();

      await expect(page).toHaveURL(new RegExp(`/athletes/${athlete.id}\\?tab=anthropometry`), {
        timeout: 15_000,
      });
      await expect(row).toContainText('Circa-PHV', { timeout: 15_000 });
      await expect(row).toContainText('85');

      // Detalle de la medición (modal) también refleja la nueva etapa.
      await row.locator('td').first().click();
      const detail = page.getByRole('dialog');
      await expect(detail).toBeVisible();
      await expect(detail).toContainText('Circa-PHV');
      await detail.getByRole('button', { name: 'Cerrar' }).first().click();
      await expect(detail).toBeHidden();

      await row.getByRole('button', { name: `Eliminar la medición del ${toDisplayDate(date)}` }).click();
      const confirm = page.getByRole('alertdialog', {
        name: `¿Eliminar la medición del ${toDisplayDate(date)}?`,
      });
      await expect(confirm).toBeVisible();
      await confirm.getByRole('button', { name: 'Eliminar' }).click();
      await expect(confirm).toBeHidden({ timeout: 15_000 });
      await expect(page.getByText('No hay mediciones registradas aún.')).toBeVisible({
        timeout: 15_000,
      });
      expect(await listRecords(page.request, athlete.id)).toHaveLength(0);
    } finally {
      await cleanupAthlete(page.request, athlete.id);
    }
  });

  test('coach2 no ve acciones sobre una medición de coach y un PUT directo devuelve 403', async ({
    page,
  }) => {
    const athlete = await createSyntheticAthlete(page.request, { tag: 'Autor' });
    try {
      const date = daysAgoIso(45);
      const record = await createRecord(page.request, athlete.id, {
        evaluation_date: date,
        weight_kg: 42,
        standing_height_cm: 152,
        sitting_height_cm: 76,
      });

      await loginAsCoach(page, COACH2_EMAIL, COACH2_PASSWORD);
      await page.goto(`/athletes/${athlete.id}?tab=anthropometry`);
      const row = historyRow(page, date);
      await expect(row).toHaveCount(1, { timeout: 15_000 });
      await expect(page.getByRole('link', { name: /editar la medición/i })).toHaveCount(0);
      await expect(page.getByRole('button', { name: /eliminar la medición/i })).toHaveCount(0);

      const coach2 = await authHeaders(page.request, 'coach2');
      const coach2View = await listRecords(page.request, athlete.id, 'coach2');
      expect(coach2View[0]?.can_modify).toBe(false);

      const put = await page.request.put(
        `${apiBaseUrl()}/api/athletes/${athlete.id}/anthropometry/${record.id}`,
        {
          headers: coach2,
          data: {
            evaluation_date: date,
            weight_kg: 43,
            standing_height_cm: 152,
            sitting_height_cm: 76,
            arm_span_cm: null,
            notes: null,
          },
        },
      );
      expect(put.status()).toBe(403);
      expect(await put.json()).toMatchObject({ detail: 'not_record_author' });

      const del = await page.request.delete(
        `${apiBaseUrl()}/api/athletes/${athlete.id}/anthropometry/${record.id}`,
        { headers: coach2 },
      );
      expect(del.status()).toBe(403);
      // Nada cambió.
      const after = await listRecords(page.request, athlete.id);
      expect(Number(after[0].weight_kg)).toBe(42);
    } finally {
      await cleanupAthlete(page.request, athlete.id);
    }
  });

  test('la familia no ve acciones, ni el marcador «Revisar», ni los campos del coach', async ({
    page,
  }) => {
    // Medición implausible (razón sentado/de pie 0,46 < 0,47) en una fecha
    // anterior a todo el seed, para que el coach SÍ tenga un «Revisar» que la
    // familia no debe ver. Se borra al final.
    const date = '2025-01-15';
    const coachHeaders = await authHeaders(page.request, 'coach');
    let record: ApiRecord | undefined = (await listRecords(page.request, PARENT_CHILD_ID)).find(
      (r) => r.evaluation_date.slice(0, 10) === date,
    );
    if (!record) {
      record = await createRecord(page.request, PARENT_CHILD_ID, {
        evaluation_date: date,
        weight_kg: 39.5,
        standing_height_cm: 149,
        sitting_height_cm: 69,
      });
    }
    try {
      const coachView = (await listRecords(page.request, PARENT_CHILD_ID)).find(
        (r) => r.id === record?.id,
      );
      expect(coachView?.plausibility_flags ?? []).toContain('sitting_ratio_atypical');

      const parentPayloads: unknown[] = [];
      page.on('response', async (response) => {
        const url = new URL(response.url());
        if (url.pathname === `/api/athletes/${PARENT_CHILD_ID}/anthropometry` && response.ok()) {
          parentPayloads.push(await response.json().catch(() => null));
        }
      });

      await loginAsCoach(page, PARENT_EMAIL, PARENT_PASSWORD);
      await page.goto(`/my-athletes/${PARENT_CHILD_ID}?tab=growth`);
      const row = historyRow(page, date);
      await expect(row).toHaveCount(1, { timeout: 15_000 });

      await expect(page.getByTestId('history-plausibility-badge')).toHaveCount(0);
      await expect(page.getByRole('link', { name: /editar la medición/i })).toHaveCount(0);
      await expect(page.getByRole('button', { name: /eliminar la medición/i })).toHaveCount(0);

      expect(parentPayloads.length, 'la familia pidió su historial').toBeGreaterThan(0);
      for (const payload of parentPayloads) {
        for (const item of payload as Array<Record<string, unknown>>) {
          expect(item).not.toHaveProperty('can_modify');
          expect(item).not.toHaveProperty('plausibility_flags');
        }
      }
    } finally {
      if (record) {
        await page.request.delete(
          `${apiBaseUrl()}/api/athletes/${PARENT_CHILD_ID}/anthropometry/${record.id}`,
          { headers: coachHeaders },
        );
      }
    }
  });
});
