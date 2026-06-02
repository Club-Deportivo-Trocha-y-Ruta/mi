// Requiere: docker compose up
import { test, expect } from '@playwright/test';

// ---------------------------------------------------------------------------
// Credenciales
// ---------------------------------------------------------------------------

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';

const PARENT_EMAIL = 'padre@trochayruta.com';
const PARENT_PASSWORD = 'Parent2026!';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function loginAsCoach(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function loginAsParent(page: import('@playwright/test').Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(PARENT_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(PARENT_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// E2E-PAD-001 — Login como padre redirige a /my-athletes
test('E2E-PAD-001: login con padre@trochayruta.com redirige a /my-athletes', async ({ page }) => {
  await loginAsParent(page);
  await expect(page).toHaveURL(/\/my-athletes/);
});

// E2E-PAD-002 — Portal padre muestra sus atletas vinculados
test('E2E-PAD-002: parent ve dashboard con sus atletas vinculados (Santiago)', async ({ page }) => {
  await loginAsParent(page);
  await expect(page).toHaveURL(/\/my-athletes/);
  // El seed vincula padre@trochayruta.com con Santiago López. La card del
  // atleta expone un link "Ver detalle de <nombre>" — usamos ese rol/nombre
  // para evitar el strict-mode violation con otras menciones de "Santiago"
  // (athlete-switcher del header, texto de sesiones).
  await expect(
    page.getByRole('link', { name: /ver detalle de santiago/i }),
  ).toBeVisible();
});

// E2E-PAD-003 — Parent navega al detalle del atleta
test('E2E-PAD-003: parent navega al detalle del atleta via "Ver detalle"', async ({ page }) => {
  await loginAsParent(page);
  await expect(page).toHaveURL(/\/my-athletes/);

  // Clic en el link de detalle del atleta. OJO: la card de "próxima sesión"
  // también tiene un link "Ver detalle de la última sesión…" que navega a
  // /parents/training/sessions/{id}. Scope al link específico del atleta
  // ("Ver detalle de <nombre>") para no clickar el de sesión.
  await page
    .getByRole('link', { name: /ver detalle de santiago/i })
    .first()
    .click();

  // URL cambia a /my-athletes/{id}
  await expect(page).toHaveURL(/\/my-athletes\/\d+/);
});

// E2E-PAD-004 — Parent no puede acceder a /athletes, redirige a /my-athletes
test('E2E-PAD-004: parent no puede acceder a /athletes (redirige a /my-athletes)', async ({ page }) => {
  await loginAsParent(page);
  await page.goto('/athletes');
  await expect(page).toHaveURL(/\/my-athletes/);
});

// E2E-PAD-005 — Coach ve sección "Padres" en el sidebar
test('E2E-PAD-005: coach ve sección "Padres" en el sidebar', async ({ page }) => {
  await loginAsCoach(page);
  await expect(page.getByRole('link', { name: /padres/i })).toBeVisible();
});

// E2E-PAD-006 — Coach navega a lista de padres y ve a Carlos García
test('E2E-PAD-006: coach navega a lista de padres y ve a Carlos García del seed', async ({ page }) => {
  await loginAsCoach(page);
  await page.getByRole('link', { name: /padres/i }).click();
  await expect(page).toHaveURL(/\/parents/);
  // El seed tiene varios "Carlos" (Carlos Ríos repetido). Apuntamos al link
  // exacto del padre "Carlos Garcia" para evitar strict-mode violation.
  await expect(
    page.getByRole('link', { name: /^Carlos Garcia$/i }),
  ).toBeVisible();
});

// E2E-PAD-007 — Coach navega al detalle de un padre
test('E2E-PAD-007: coach navega al detalle de Carlos García via link "Ver"', async ({ page }) => {
  await loginAsCoach(page);
  await page.goto('/parents');
  await expect(page).toHaveURL(/\/parents/);

  // Clic en "Ver" de la fila de Carlos García
  await page.getByRole('link', { name: /^Ver$/ }).first().click();

  // URL cambia a /parents/{id}
  await expect(page).toHaveURL(/\/parents\/\d+/);
});
