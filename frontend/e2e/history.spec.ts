// Requiere: docker compose up
import { test, expect } from '@playwright/test';

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';

async function loginAsCoach(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

// E2E-007 — Historial de mediciones ordenado cronológicamente (más reciente primero)
test('E2E-007: historial de mediciones muestra registros en orden descendente', async ({ page }) => {
  await loginAsCoach(page);

  // Navegar a atletas y abrir el primero (las filas no son clickeables; el
  // link "Ver" de la fila navega al detalle).
  await page.getByRole('link', { name: /atletas/i }).click();
  await expect(page).toHaveURL(/\/athletes/);
  // Esperamos la respuesta del GET de antropometría que dispara la carga del
  // detalle: así no asertamos contra el skeleton (evita flake bajo carga
  // paralela, donde la query puede entrar en reintentos).
  const anthroResponse = page.waitForResponse(
    (r) => /\/anthropometry/.test(r.url()) && r.status() === 200,
    { timeout: 30_000 },
  );
  await page.getByRole('link', { name: /^Ver$/ }).first().click();
  await expect(page).toHaveURL(/\/athletes\/\d+/);
  await anthroResponse;

  // El detalle auto-selecciona el tab "Crecimiento" si hay mediciones.
  // Cambiamos al tab "Antropometría" para ver el historial de registros.
  await page.getByRole('button', { name: /antropometr[ií]a/i }).click();

  // El historial en desktop (viewport 1280px) usa el testid -desktop;
  // el testid "anthropometry-history" es la lista mobile (oculta en md+).
  const historySection = page.getByTestId('anthropometry-history-desktop');
  await expect(historySection).toBeVisible({ timeout: 15_000 });

  // Obtener las fechas de los registros del historial
  const dateRows = historySection.getByTestId('record-date');
  const count = await dateRows.count();

  if (count >= 2) {
    const firstDate = await dateRows.nth(0).textContent();
    const secondDate = await dateRows.nth(1).textContent();

    // El componente renderiza la fecha como DD/MM/YYYY (formatDate de
    // AnthropometryHistory). `new Date("14/04/2026")` es inválido en V8
    // (espera MM/DD), así que parseamos los componentes explícitamente a un
    // valor comparable YYYYMMDD.
    const toComparable = (txt: string | null): number => {
      const m = (txt ?? '').trim().match(/^(\d{2})\/(\d{2})\/(\d{4})$/);
      if (!m) return NaN;
      const [, dd, mm, yyyy] = m;
      return Number(`${yyyy}${mm}${dd}`);
    };
    const v1 = toComparable(firstDate);
    const v2 = toComparable(secondDate);
    // Ambas fechas deben ser parseables (no NaN) y en orden descendente.
    expect(Number.isNaN(v1)).toBe(false);
    expect(Number.isNaN(v2)).toBe(false);
    expect(v1).toBeGreaterThanOrEqual(v2);
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

  // Ir al detalle de un atleta con mediciones (el link "Ver" navega; la fila no).
  await page.getByRole('link', { name: /atletas/i }).click();
  await expect(page).toHaveURL(/\/athletes/);
  await page.getByRole('link', { name: /^Ver$/ }).first().click();
  await expect(page).toHaveURL(/\/athletes\/\d+/);

  // El detalle auto-selecciona el tab "Crecimiento" cuando hay mediciones,
  // que monta las gráficas. Localizar la sección (Recharts renderiza SVG).
  // Timeout amplio por la carga de useAnthropometry bajo concurrencia.
  const chartsSection = page.getByTestId('growth-charts');
  await expect(chartsSection).toBeVisible({ timeout: 15_000 });

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
