// Requiere: docker compose up
import { test, expect } from '@playwright/test';

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';

// E2E-001 — Login y acceso al dashboard
test('E2E-001: login exitoso redirige al dashboard y guarda token en sessionStorage', async ({ page }) => {
  await page.goto('/login');

  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /ingresar/i }).click();

  // Verificar redirección al dashboard (no está en /login)
  await expect(page).not.toHaveURL(/\/login/);

  // Verificar que el NOMBRE del usuario aparece en el header (no el rol).
  // El AppShell renderiza `{first_name} {last_name}`; el coach del seed
  // (entrenador@trochyruta.com) se llama "Juan Diaz".
  await expect(page.getByRole('banner')).toContainText(/Juan Diaz/i);

  // PRIV-001: token en sessionStorage (clave 'auth-session'), no en localStorage
  const sessionData = await page.evaluate(() =>
    sessionStorage.getItem('auth-session')
  );
  const localToken = await page.evaluate(() =>
    localStorage.getItem('auth-session')
  );
  expect(sessionData).not.toBeNull();
  const parsed = JSON.parse(sessionData!);
  expect(parsed.state.isAuthenticated).toBe(true);
  expect(localToken).toBeNull();
});

// E2E-002 — Login fallido muestra error
test('E2E-002: login fallido permanece en /login y muestra mensaje de error', async ({ page }) => {
  await page.goto('/login');

  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill('ContraseñaIncorrecta!');
  await page.getByRole('button', { name: /ingresar/i }).click();

  // Permanece en /login
  await expect(page).toHaveURL(/\/login/);

  // Muestra mensaje de error
  await expect(page.getByText(/credenciales inválidas/i)).toBeVisible();

  // Sin token guardado
  const sessionData = await page.evaluate(() =>
    sessionStorage.getItem('auth-session')
  );
  const parsed = sessionData ? JSON.parse(sessionData) : null;
  expect(parsed?.state?.isAuthenticated ?? false).toBe(false);
});

// E2E-009 — Acceso denegado a rutas protegidas sin login
test('E2E-009: acceso directo a /athletes sin autenticación redirige a /login', async ({ page }) => {
  // Navegar directamente sin autenticarse
  await page.goto('/athletes');

  // Debe redirigir a /login
  await expect(page).toHaveURL(/\/login/);

  // No se expone contenido protegido
  await expect(page.getByRole('table')).not.toBeVisible();
});

// E2E-010 — Logout limpia la sesión
test('E2E-010: logout limpia sesión y redirige a /login', async ({ page }) => {
  // Login previo
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);

  // Click en logout
  await page.getByRole('button', { name: /cerrar sesión/i }).click();

  // Redirige a /login
  await expect(page).toHaveURL(/\/login/);

  // sessionStorage limpiado (isAuthenticated = false)
  const sessionData = await page.evaluate(() =>
    sessionStorage.getItem('auth-session')
  );
  const parsed = sessionData ? JSON.parse(sessionData) : null;
  expect(parsed?.state?.isAuthenticated ?? false).toBe(false);

  // Navegar a /athletes debe redirigir de vuelta a /login
  await page.goto('/athletes');
  await expect(page).toHaveURL(/\/login/);
});
