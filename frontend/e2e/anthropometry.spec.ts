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

async function navigateToFirstAthlete(page: import('@playwright/test').Page) {
  await page.getByRole('link', { name: /atletas/i }).click();
  await expect(page).toHaveURL(/\/athletes/);
  // Click en el primer atleta de la tabla
  await page.getByRole('table').getByRole('row').nth(1).click();
  await expect(page).toHaveURL(/\/athletes\/\d+/);
}

// E2E-005 — Registrar medición antropométrica y ver PHV calculado
test('E2E-005: registrar medición antropométrica y verificar cálculo PHV', async ({ page }) => {
  await loginAsCoach(page);
  await navigateToFirstAthlete(page);

  // Cambiar a la tab de Antropometría
  await page.getByRole('button', { name: /antropometria/i }).click();

  // Abrir formulario de nueva medición
  await page.getByRole('button', { name: /nueva medicion/i }).click();

  // Completar los campos numéricos — el panel PHV preview se activa en tiempo real
  await page.getByLabel(/peso \(kg\)/i).fill('45.5');
  await page.getByLabel(/talla de pie/i).fill('155.0');
  await page.getByLabel(/talla sentado/i).fill('73.0');

  // Verificar panel PHV en tiempo real antes de guardar
  await expect(page.getByTestId('leg-length')).toContainText('82');
  await expect(page.getByTestId('maturity-offset')).toBeVisible();
  await expect(page.getByTestId('age-at-phv')).toBeVisible();

  const maturationStatus = page.getByTestId('maturation-status');
  await expect(maturationStatus).toBeVisible();
  const statusText = await maturationStatus.textContent();
  expect(['Pre-PHV', 'Circa-PHV', 'Post-PHV'].some(s => statusText?.includes(s))).toBeTruthy();

  // Completar fecha y guardar
  await page.getByLabel(/fecha de evaluacion/i).fill('2026-04-14');
  await page.getByRole('button', { name: /guardar medicion/i }).click();

  // El formulario desaparece y el historial muestra la nueva medición
  await expect(page.getByTestId('anthropometry-history')).toBeVisible();
});

// E2E-006 — Previsualización PHV en tiempo real durante el formulario
test('E2E-006: previsualización PHV se actualiza en tiempo real al completar campos', async ({ page }) => {
  await loginAsCoach(page);
  await navigateToFirstAthlete(page);

  // Cambiar a la tab de Antropometría
  await page.getByRole('button', { name: /antropometria/i }).click();

  // Abrir formulario de nueva medición
  await page.getByRole('button', { name: /nueva medicion/i }).click();

  // El panel PHV siempre está visible (muestra mensaje de "Completa los campos")
  const phvPreview = page.getByTestId('phv-preview');
  await expect(phvPreview).toBeVisible();

  // Ingresar peso
  await page.getByLabel(/peso \(kg\)/i).fill('45.5');
  // Ingresar talla de pie
  await page.getByLabel(/talla de pie/i).fill('155.0');
  // Ingresar talla sentado — a partir de aquí se activa el cálculo real
  await page.getByLabel(/talla sentado/i).fill('73.0');

  // La sección de Vista previa PHV muestra datos calculados (ya no el mensaje vacío)
  await expect(page.getByTestId('leg-length')).toBeVisible();
  await expect(page.getByTestId('maturation-status')).toBeVisible();
});
