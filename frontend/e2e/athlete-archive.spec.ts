// Requiere: docker compose up (o el stack e2e aislado)
//
// E2E — Archivar (soft delete) un atleta y restaurarlo (feature 041, US2).
// Contrato: specs/041-multi-coach-governance/contracts/athlete-archive.md
//
// Cubre: FR-014 (desaparece de la lista activa), FR-015 (solo admin
// restaura), y que la evidencia de consentimiento parental sobrevive (§6 —
// no se valida la fila de la DB directamente, sino que el atleta sigue
// existiendo y siendo restaurable, lo que exige que nada se haya borrado).
//
// Datos: crea un atleta sintético por corrida ("Ficticio") vía la UI para no
// interferir con el seed ni con otros specs en paralelo.
import { test, expect, type APIRequestContext, type Page } from '@playwright/test';
import { realTokens } from './helpers/session';

const ADMIN_EMAIL = 'admin@trochyruta.com';
const ADMIN_PASSWORD = 'Admin2026!';

function apiBaseUrl(): string {
  return process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';
}

async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(ADMIN_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(ADMIN_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/** Crea un atleta sintético directo por API (coach), para no acoplar el spec a un wizard largo. */
async function createSyntheticAthlete(request: APIRequestContext): Promise<number> {
  const tokens = await realTokens(request, 'coach');
  const stamp = Date.now();
  const res = await request.post(`${apiBaseUrl()}/api/athletes`, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
    data: {
      first_name: 'Atleta',
      last_name: `ArchivoE2E${stamp}`,
      birth_date: '2014-05-10',
      sex: 'M',
      club_join_date: '2025-01-10',
    },
  });
  expect(res.ok(), `creación de atleta sintético falló: ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { id: number };
  return body.id;
}

test.describe('Athlete archive E2E', () => {
  test('E2E-ARCH-001: archivar un atleta lo quita de la lista activa y lo muestra en el archivo admin', async ({
    page,
  }) => {
    const athleteId = await createSyntheticAthlete(page.request);

    await loginAsAdmin(page);
    await page.goto(`/athletes/${athleteId}/edit`);
    await expect(page.getByTestId('archive-athlete-button')).toBeVisible({ timeout: 10_000 });

    await page.getByTestId('archive-athlete-button').click();
    await expect(page.getByTestId('archive-athlete-dialog')).toBeVisible();

    // Selecciona un motivo del catálogo cerrado (nunca texto libre — FR-003).
    await page.getByTestId('archive-reason-select').click();
    await page.getByRole('option').first().click();
    await page.getByTestId('archive-confirm-button').click();

    // Tras archivar, navega fuera del form (al listado) — ya no editable.
    await expect(page).toHaveURL(/\/athletes(?!\/\d)/, { timeout: 10_000 });

    // No aparece en la lista activa.
    await page.goto('/athletes');
    await expect(page.getByText(new RegExp(`ArchivoE2E`))).toHaveCount(0);

    // Sí aparece en la vista admin de archivados, con evidencia intacta
    // (el registro sigue existiendo — restaurable, no borrado).
    await page.goto('/admin/atletas-archivados');
    await expect(page.getByTestId('archived-athletes-page')).toBeVisible({ timeout: 10_000 });
    const archivedRow = page.getByTestId('archived-athlete-row').filter({ hasText: 'ArchivoE2E' });
    await expect(archivedRow).toBeVisible({ timeout: 10_000 });
  });

  test('E2E-ARCH-002: restaurar un atleta archivado lo devuelve a la lista activa (solo admin)', async ({
    page,
  }) => {
    const athleteId = await createSyntheticAthlete(page.request);

    // Archiva por API directamente (coach) para llegar rápido al estado a probar.
    const tokens = await realTokens(page.request, 'coach');
    const archiveRes = await page.request.delete(`${apiBaseUrl()}/api/athletes/${athleteId}`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
      data: { reason_code: 'athlete_left_club' },
    });
    expect(archiveRes.ok(), `archivar por API falló: ${archiveRes.status()}`).toBeTruthy();

    await loginAsAdmin(page);
    await page.goto('/admin/atletas-archivados');
    await expect(page.getByTestId('archived-athletes-page')).toBeVisible({ timeout: 10_000 });

    const archivedRow = page.getByTestId('archived-athlete-row').filter({ hasText: 'ArchivoE2E' });
    await expect(archivedRow).toBeVisible({ timeout: 10_000 });

    await archivedRow.getByTestId('restore-athlete-button').click();
    const restoreDialog = page.getByRole('dialog');
    await expect(restoreDialog).toBeVisible();
    const reasonControl = restoreDialog.getByRole('combobox').first();
    if (await reasonControl.count()) {
      await reasonControl.click();
      await page.getByRole('option').first().click();
    }
    await restoreDialog.getByRole('button', { name: /restaurar|confirmar/i }).click();

    // Ya no está en la lista de archivados.
    await expect(archivedRow).toHaveCount(0, { timeout: 10_000 });

    // Vuelve a aparecer como atleta activo.
    await page.goto('/athletes');
    await expect(page.getByText(new RegExp(`ArchivoE2E`))).toBeVisible({ timeout: 10_000 });
  });
});
