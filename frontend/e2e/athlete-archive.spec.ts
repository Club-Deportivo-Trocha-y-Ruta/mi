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

/**
 * Crea un atleta sintético directo por API (coach), para no acoplar el spec
 * a un wizard largo. Devuelve también el `lastName` único de esta corrida
 * (incluye el timestamp) — el stack e2e acumula atletas sintéticos de
 * corridas anteriores (ver CLAUDE.md del task: "make specs robust to
 * re-runs"), así que filtrar solo por el prefijo `ArchivoE2E` produce
 * "strict mode violation" de Playwright (varias filas matchean) apenas la
 * segunda vez que corre este spec contra el mismo stack.
 */
async function createSyntheticAthlete(
  request: APIRequestContext,
): Promise<{ id: number; lastName: string }> {
  const tokens = await realTokens(request, 'coach');
  const headers = { Authorization: `Bearer ${tokens.access_token}` };
  // `club_id` es obligatorio en `AthleteCreate` (backend/app/schemas/athlete.py) —
  // se toma del propio coach en vez de asumir club 1 (multi-club, feature 041).
  const meRes = await request.get(`${apiBaseUrl()}/api/auth/me`, { headers });
  expect(meRes.ok(), `GET /auth/me falló: ${meRes.status()}`).toBeTruthy();
  const me = (await meRes.json()) as { club_ids: number[] };
  // `Date.now()` solo no basta: E2E-ARCH-001 y E2E-ARCH-002 corren en
  // paralelo (workers distintos) y pueden pedir la marca de tiempo en el
  // mismo milisegundo, colisionando en el mismo `last_name` — dos filas
  // distintas con el mismo texto rompen los locators por substring de
  // ambos tests ("strict mode violation"). Se agrega un sufijo aleatorio.
  const lastName = `ArchivoE2E${Date.now()}${Math.floor(Math.random() * 1_000_000)}`;
  const res = await request.post(`${apiBaseUrl()}/api/athletes`, {
    headers,
    data: {
      first_name: 'Atleta',
      last_name: lastName,
      birth_date: '2014-05-10',
      sex: 'M',
      club_join_date: '2025-01-10',
      club_id: me.club_ids[0],
    },
  });
  expect(res.ok(), `creación de atleta sintético falló: ${res.status()}`).toBeTruthy();
  const body = (await res.json()) as { id: number };
  return { id: body.id, lastName };
}

test.describe('Athlete archive E2E', () => {
  test('E2E-ARCH-001: archivar un atleta lo quita de la lista activa y lo muestra en el archivo admin', async ({
    page,
  }) => {
    const { id: athleteId, lastName } = await createSyntheticAthlete(page.request);

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
    await expect(page.getByText(lastName)).toHaveCount(0);

    // Sí aparece en la vista admin de archivados, con evidencia intacta
    // (el registro sigue existiendo — restaurable, no borrado).
    await page.goto('/admin/atletas-archivados');
    await expect(page.getByTestId('archived-athletes-page')).toBeVisible({ timeout: 10_000 });
    const archivedRow = page.getByTestId('archived-athlete-row').filter({ hasText: lastName });
    await expect(archivedRow).toBeVisible({ timeout: 10_000 });
  });

  test('E2E-ARCH-002: restaurar un atleta archivado lo devuelve a la lista activa (solo admin)', async ({
    page,
  }) => {
    const { id: athleteId, lastName } = await createSyntheticAthlete(page.request);

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

    const archivedRow = page.getByTestId('archived-athlete-row').filter({ hasText: lastName });
    await expect(archivedRow).toBeVisible({ timeout: 10_000 });

    await archivedRow.getByTestId('restore-athlete-button').click();
    // `RestoreAthleteDialog` usa el `AlertDialog` de Radix (role="alertdialog",
    // no "dialog" — components/athletes/RestoreAthleteDialog.tsx), con su
    // propio testid `restore-athlete-dialog`.
    const restoreDialog = page.getByTestId('restore-athlete-dialog');
    await expect(restoreDialog).toBeVisible();
    // El motivo es obligatorio (handleConfirm bloquea sin él) — nunca opcional.
    await restoreDialog.getByTestId('restore-reason-select').click();
    await page.getByRole('option').first().click();
    await restoreDialog.getByTestId('restore-confirm-button').click();

    // Ya no está en la lista de archivados.
    await expect(archivedRow).toHaveCount(0, { timeout: 10_000 });

    // Vuelve a aparecer como atleta activo. `AthletesTable` renderiza la
    // fila dos veces — `<ul className="... md:hidden">` (mobile) seguido de
    // `<table>` (desktop, `hidden md:block`) — ambas en el DOM a la vez;
    // en el viewport desktop por defecto de Playwright la `<ul>` (la
    // primera coincidencia en el DOM) queda oculta por CSS, así que se
    // toma la última coincidencia (la fila de la tabla) en vez de `.first()`.
    await page.goto('/athletes');
    await expect(page.getByText(lastName).last()).toBeVisible({ timeout: 10_000 });
  });
});
