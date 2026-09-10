// Requiere: docker compose up (o el stack e2e aislado, frontend/scripts/e2e-stack.sh)
//
// E2E — Administración de personal (feature 041 — gobernanza multi-coach, US3).
// Contrato: specs/041-multi-coach-governance/contracts/staff-admin.md
//
// Cubre: acceso admin-only a /admin/usuarios, creación de un entrenador con
// club obligatorio (§1.2 fila 4), y desactivar en vez de borrar (§4).
// Datos: solo cuentas sintéticas del seed (`backend/scripts/seed.py`).
import { test, expect, type Page } from '@playwright/test';

const ADMIN_EMAIL = 'admin@trochyruta.com';
const ADMIN_PASSWORD = 'Admin2026!';

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';

async function loginAsAdmin(page: Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(ADMIN_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(ADMIN_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function loginAsCoach(page: Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test.describe('Staff admin E2E', () => {
  test('E2E-STAFF-001: admin accede a /admin/usuarios y ve la tabla de personal', async ({
    page,
  }) => {
    await loginAsAdmin(page);
    await page.goto('/admin/usuarios');
    await expect(page.getByTestId('staff-page')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('staff-table')).toBeVisible({ timeout: 10_000 });
  });

  test('E2E-STAFF-002: un coach que navega a /admin/usuarios no ve la pantalla de administración', async ({
    page,
  }) => {
    await loginAsCoach(page);
    await page.goto('/admin/usuarios');
    // Ruta admin-only: el guard de RBAC del router redirige o bloquea el
    // acceso — en cualquier caso, la tabla de personal no debe renderizarse
    // para un coach.
    await expect(page.getByTestId('staff-page')).toHaveCount(0);
  });

  test('E2E-STAFF-003: crear entrenador exige seleccionar club (validación 422 sin club_id)', async ({
    page,
  }) => {
    await loginAsAdmin(page);
    await page.goto('/admin/usuarios');
    await expect(page.getByTestId('staff-table')).toBeVisible({ timeout: 10_000 });

    await page.getByTestId('staff-new-button').click();
    await expect(page.getByTestId('staff-create-sheet')).toBeVisible();

    // Nombre único por corrida para no chocar con el seed ni con corridas
    // previas del mismo stack e2e.
    const stamp = Date.now();
    await page.getByLabel(/nombres/i).fill('Camila Ficticia');
    await page.getByLabel(/apellidos/i).fill('Prueba E2E');
    await page.getByLabel(/correo/i).fill(`camila.e2e.${stamp}@trochayruta-test.com`);

    // Sin elegir club: el submit debe fallar con el 422 del contrato §1.2
    // fila 4 ("El club es obligatorio para las cuentas de entrenador...").
    await page.getByRole('button', { name: /crear|guardar|invitar/i }).click();

    await expect(page.getByText(/club.*obligatorio/i)).toBeVisible({ timeout: 5_000 });
    // El sheet permanece abierto: la creación no debe haberse disparado.
    await expect(page.getByTestId('staff-create-sheet')).toBeVisible();
  });

  test('E2E-STAFF-004: crear entrenador con club asignado aparece en la tabla, luego se desactiva (no se borra)', async ({
    page,
  }) => {
    await loginAsAdmin(page);
    await page.goto('/admin/usuarios');
    await expect(page.getByTestId('staff-table')).toBeVisible({ timeout: 10_000 });

    const stamp = Date.now();
    const email = `mateo.e2e.${stamp}@trochayruta-test.com`;

    await page.getByTestId('staff-new-button').click();
    await expect(page.getByTestId('staff-create-sheet')).toBeVisible();

    await page.getByLabel(/nombres/i).fill('Mateo Ficticio');
    await page.getByLabel(/apellidos/i).fill('Prueba E2E');
    await page.getByLabel(/correo/i).fill(email);

    // Selecciona el primer club disponible del combo (seed tiene al menos uno).
    const clubTrigger = page.getByRole('combobox', { name: /club/i });
    await clubTrigger.click();
    await page.getByRole('option').first().click();

    await page.getByRole('button', { name: /crear|guardar|invitar/i }).click();
    await expect(page.getByTestId('staff-create-sheet')).toBeHidden({ timeout: 10_000 });

    // La nueva fila aparece en la tabla, activa por defecto.
    const row = page.locator('tr', { hasText: email });
    await expect(row).toBeVisible({ timeout: 10_000 });
    await expect(row.getByText(/activo/i)).toBeVisible();

    // Desactivar (no DELETE): abrir el diálogo de estado, elegir motivo y confirmar.
    await row.getByRole('button', { name: /desactivar/i }).click();
    const stateDialog = page.getByRole('dialog');
    await expect(stateDialog).toBeVisible();

    // Selecciona un motivo del catálogo cerrado si el diálogo lo pide (select/radio).
    const reasonControl = stateDialog.getByRole('combobox').first();
    if (await reasonControl.count()) {
      await reasonControl.click();
      await page.getByRole('option').first().click();
    }
    await stateDialog.getByRole('button', { name: /desactivar|confirmar/i }).click();

    // La fila sigue existiendo (no fue borrada) pero ahora está inactiva.
    await expect(row).toBeVisible({ timeout: 10_000 });
    await expect(row.getByText(/inactivo/i)).toBeVisible();
  });
});
