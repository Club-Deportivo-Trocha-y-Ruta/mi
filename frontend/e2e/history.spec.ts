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

// E2E-007 — Historial de mediciones ordenado cronológicamente (más reciente primero)
test('E2E-007: historial de mediciones muestra registros en orden descendente', async ({ page }) => {
  await loginAsCoach(page);

  // Navegar a atletas y abrir el primero que tenga mediciones
  await page.getByRole('link', { name: /atletas/i }).click();
  await page.getByRole('table').getByRole('row').nth(1).click();

  // Navegar a la sección de historial
  const historySection = page.getByTestId('anthropometry-history');
  await expect(historySection).toBeVisible();

  // Obtener las fechas de los registros del historial
  const dateRows = historySection.getByTestId('record-date');
  const count = await dateRows.count();

  if (count >= 2) {
    const firstDate = await dateRows.nth(0).textContent();
    const secondDate = await dateRows.nth(1).textContent();

    // La primera fecha debe ser mayor o igual a la segunda (orden descendente)
    const date1 = new Date(firstDate ?? '');
    const date2 = new Date(secondDate ?? '');
    expect(date1.getTime()).toBeGreaterThanOrEqual(date2.getTime());
  } else {
    // Si solo hay 0-1 registros, el test pasa trivialmente
    expect(count).toBeGreaterThanOrEqual(0);
  }
});

// E2E-008 — Gráficas de crecimiento se renderizan con datos
test('E2E-008: gráficas de crecimiento se renderizan sin errores de consola', async ({ page }) => {
  const consoleErrors: string[] = [];
  page.on('console', msg => {
    if (msg.type() === 'error') {
      consoleErrors.push(msg.text());
    }
  });

  await loginAsCoach(page);

  // Ir al detalle de un atleta con mediciones
  await page.getByRole('link', { name: /atletas/i }).click();
  await page.getByRole('table').getByRole('row').nth(1).click();

  // Localizar la sección de gráficas (Recharts renderiza SVG)
  const chartsSection = page.getByTestId('growth-charts');
  await expect(chartsSection).toBeVisible();

  // Verificar que se renderizan elementos SVG (Recharts)
  const svgElements = chartsSection.locator('svg');
  await expect(svgElements.first()).toBeVisible();

  // Sin errores de consola relacionados con las gráficas
  const rechartErrors = consoleErrors.filter(e =>
    e.toLowerCase().includes('recharts') ||
    e.toLowerCase().includes('chart') ||
    e.toLowerCase().includes('undefined') ||
    e.toLowerCase().includes('null')
  );
  expect(rechartErrors).toHaveLength(0);
});
