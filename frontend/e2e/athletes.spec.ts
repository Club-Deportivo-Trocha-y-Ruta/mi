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

// E2E-003 — Crear atleta masculino y verificar categoría
test('E2E-003: crear atleta masculino muestra categoría Pre-juvenil A', async ({ page }) => {
  await loginAsCoach(page);

  // Navegar a sección de atletas
  await page.getByRole('link', { name: /atletas/i }).click();
  await expect(page).toHaveURL(/\/athletes/);

  // Abrir formulario de creación. El acceso es un link "+ Agregar atleta"
  // (no un botón), que navega a /athletes/new.
  await page.getByRole('link', { name: /agregar atleta/i }).first().click();
  await expect(page).toHaveURL(/\/athletes\/new/);

  // Completar formulario. Los campos del AthleteForm son: Nombres, Apellidos,
  // Fecha de nacimiento, Sexo, Fecha ingreso al club (NO hay "años en el club").
  await page.getByLabel(/nombres/i).fill('Santiago');
  await page.getByLabel(/apellidos/i).fill('López');
  await page.getByLabel(/fecha de nacimiento/i).fill('2013-06-15');
  await page.getByLabel(/sexo/i).selectOption('M');

  // Enviar (botón submit "Crear atleta").
  await page.getByRole('button', { name: /crear atleta/i }).click();

  // Tras crear, la app navega al detalle del atleta (/athletes/{id}).
  await expect(page).toHaveURL(/\/athletes\/\d+/, { timeout: 15_000 });

  // El detalle muestra el nombre y la categoría calculada (2013 + M = Pre-juvenil A).
  await expect(
    page.getByRole('heading', { name: /santiago lópez/i }),
  ).toBeVisible();
  await expect(page.getByText(/Pre-juvenil A/i).first()).toBeVisible();
});

// E2E-004 — Crear atleta femenino y verificar categoría femenina
test('E2E-004: crear atleta femenino muestra categoría Infantil B femenino', async ({ page }) => {
  await loginAsCoach(page);

  await page.getByRole('link', { name: /atletas/i }).click();
  await expect(page).toHaveURL(/\/athletes/);
  await page.getByRole('link', { name: /agregar atleta/i }).first().click();
  await expect(page).toHaveURL(/\/athletes\/new/);

  await page.getByLabel(/nombres/i).fill('Valentina');
  await page.getByLabel(/apellidos/i).fill('Gómez');
  await page.getByLabel(/fecha de nacimiento/i).fill('2014-03-20');
  await page.getByLabel(/sexo/i).selectOption('F');

  await page.getByRole('button', { name: /crear atleta/i }).click();

  // Tras crear, navega al detalle; verificar categoría femenina (2014 + F).
  await expect(page).toHaveURL(/\/athletes\/\d+/, { timeout: 15_000 });
  await expect(
    page.getByRole('heading', { name: /valentina gómez/i }),
  ).toBeVisible();
  await expect(page.getByText(/Infantil B femenino/i).first()).toBeVisible();
});
