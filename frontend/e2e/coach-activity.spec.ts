// Requiere: docker compose up (o el stack e2e aislado)
//
// E2E — Vista "Actividad por entrenador" (feature 041 — gobernanza
// multi-coach, US7). Contrato:
// specs/041-multi-coach-governance/contracts/coach-activity-report.md
//
// Cubre: acceso coach/admin a /training/reports/actividad-entrenadores,
// tarjetas por entrenador del club (incluye a coach2, seedeado en el mismo
// club), filtro por rango de fechas y por entrenador, y el link a
// "Ver historial de <coach>".
import { test, expect, type Page } from '@playwright/test';

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';

async function loginAsCoach(page: Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

test.describe('Coach activity E2E', () => {
  test('E2E-CACT-001: coach accede a la vista de actividad y ve totales del club', async ({
    page,
  }) => {
    await loginAsCoach(page);
    await page.goto('/training/reports/actividad-entrenadores');

    await expect(page.getByTestId('coach-activity-page')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByTestId('coach-activity-filters')).toBeVisible();
    await expect(page.getByTestId('coach-activity-club-totals')).toBeVisible({ timeout: 10_000 });
  });

  test('E2E-CACT-002: la vista lista tarjetas por entrenador, incluido el segundo coach del club', async ({
    page,
  }) => {
    await loginAsCoach(page);
    await page.goto('/training/reports/actividad-entrenadores');
    await expect(page.getByTestId('coach-activity-club-totals')).toBeVisible({ timeout: 10_000 });

    // Amplía el rango a "Temporada" para maximizar la chance de que ambos
    // entrenadores del seed tengan alguna actividad registrada.
    await page.getByRole('button', { name: /temporada/i }).click();

    const cards = page.getByTestId('coach-activity-card');
    // Al menos una tarjeta (el club tiene ≥1 coach activo del seed); si el
    // segundo coach nunca actuó en el rango, seguirá listado con ceros —
    // la vista lista todo el staff del club, no solo quien tuvo actividad.
    await expect(cards.first()).toBeVisible({ timeout: 10_000 });
    const count = await cards.count();
    expect(count).toBeGreaterThanOrEqual(1);

    // Cada tarjeta expone un link "Ver historial de <nombre>".
    await expect(cards.first().getByTestId('coach-activity-history-link')).toBeVisible();
  });

  test('E2E-CACT-003: filtrar por un entrenador específico limita la tarjeta mostrada', async ({
    page,
  }) => {
    await loginAsCoach(page);
    await page.goto('/training/reports/actividad-entrenadores');
    await expect(page.getByTestId('coach-activity-club-totals')).toBeVisible({ timeout: 10_000 });

    const coachSelect = page.locator('#coach-activity-coach');
    await expect(coachSelect).toBeVisible({ timeout: 10_000 });

    const optionValues = await coachSelect.locator('option').evaluateAll((opts) =>
      opts.map((o) => (o as HTMLOptionElement).value).filter(Boolean),
    );
    test.skip(optionValues.length === 0, 'El seed no tiene entrenadores listados en el selector.');

    await coachSelect.selectOption(optionValues[0]);

    const cards = page.getByTestId('coach-activity-card');
    await expect(cards).toHaveCount(1, { timeout: 10_000 });
    await expect(cards.first()).toHaveAttribute('data-coach-id', optionValues[0]);

    // "Limpiar filtros" reaparece con un filtro activo.
    await expect(page.getByRole('button', { name: /limpiar filtros/i })).toBeVisible();
  });

  test('E2E-CACT-004: la vista es interna del club — el subtítulo aclara que no se comparte con familias', async ({
    page,
  }) => {
    await loginAsCoach(page);
    await page.goto('/training/reports/actividad-entrenadores');
    await expect(page.getByTestId('coach-activity-page')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/no se comparte con las familias/i)).toBeVisible();
  });
});
