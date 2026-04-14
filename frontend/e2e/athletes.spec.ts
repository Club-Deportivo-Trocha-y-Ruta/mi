// Requiere: docker compose up
import { test, expect } from '@playwright/test';

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';

async function loginAsCoach(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByLabel(/email/i).fill(COACH_EMAIL);
  await page.getByLabel(/contraseña|password/i).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

// E2E-003 — Crear atleta masculino y verificar categoría
test('E2E-003: crear atleta masculino muestra categoría Pre-juvenil A', async ({ page }) => {
  await loginAsCoach(page);

  // Navegar a sección de atletas
  await page.getByRole('link', { name: /atletas/i }).click();
  await expect(page).toHaveURL(/\/athletes/);

  // Abrir formulario de creación
  await page.getByRole('button', { name: /crear atleta/i }).click();

  // Completar formulario
  await page.getByLabel(/nombres/i).fill('Santiago');
  await page.getByLabel(/apellidos/i).fill('López');
  await page.getByLabel(/fecha de nacimiento/i).fill('2013-06-15');
  await page.getByLabel(/sexo/i).selectOption('M');
  await page.getByLabel(/años en el club/i).fill('2');

  // Enviar
  await page.getByRole('button', { name: /crear atleta/i }).click();

  // Verificar que el atleta aparece en la lista con la categoría correcta
  await expect(page.getByRole('table')).toContainText('Santiago');
  await expect(page.getByRole('table')).toContainText('Pre-juvenil A');
});

// E2E-004 — Crear atleta femenino y verificar categoría femenina
test('E2E-004: crear atleta femenino muestra categoría Infantil B femenino', async ({ page }) => {
  await loginAsCoach(page);

  await page.getByRole('link', { name: /atletas/i }).click();
  await page.getByRole('button', { name: /crear atleta/i }).click();

  await page.getByLabel(/nombres/i).fill('Valentina');
  await page.getByLabel(/apellidos/i).fill('Gómez');
  await page.getByLabel(/fecha de nacimiento/i).fill('2014-03-20');
  await page.getByLabel(/sexo/i).selectOption('F');
  await page.getByLabel(/años en el club/i).fill('1');

  await page.getByRole('button', { name: /crear atleta/i }).click();

  // Verificar categoría femenina
  await expect(page.getByRole('table')).toContainText('Valentina');
  await expect(page.getByRole('table')).toContainText('Infantil B femenino');
});
