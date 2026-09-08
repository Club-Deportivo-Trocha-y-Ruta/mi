/**
 * Helpers para localizar al atleta demo del stack e2e aislado
 * (`backend/scripts/seed.py`, `docker-compose.e2e.yml`).
 *
 * Los specs de coach no deben depender de "el primer atleta de la lista":
 * `athletes.spec.ts` crea atletas nuevos en paralelo y el orden de la tabla
 * cambia. Se resuelve por API el atleta con mediciones antropométricas
 * sembradas (el del seed) y se navega directo a su detalle.
 *
 * Las credenciales son las del seed de desarrollo (datos sintéticos), las
 * mismas que ya viven en `anthropometry.spec.ts`; nunca se apunta al stack
 * `me` con datos reales.
 */
import { expect, type APIRequestContext, type Page } from '@playwright/test';

export const COACH_EMAIL = 'entrenador@trochyruta.com';
export const COACH_PASSWORD = 'Coach2026!';

export function apiBaseUrl(): string {
  return process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';
}

async function apiToken(request: APIRequestContext): Promise<string> {
  const res = await request.post(`${apiBaseUrl()}/api/auth/login`, {
    data: { email: COACH_EMAIL, password: COACH_PASSWORD },
  });
  expect(res.ok(), 'login por API del coach demo').toBeTruthy();
  const body = (await res.json()) as { access_token: string };
  return body.access_token;
}

/**
 * Devuelve el id del atleta demo: el de menor id que tenga mediciones.
 * Si ninguno tiene, devuelve el de menor id (el sembrado primero).
 */
export async function resolveDemoAthleteId(request: APIRequestContext): Promise<number> {
  const token = await apiToken(request);
  const headers = { Authorization: `Bearer ${token}` };
  const listRes = await request.get(`${apiBaseUrl()}/api/athletes`, { headers });
  expect(listRes.ok(), 'listado de atletas por API').toBeTruthy();
  const raw = (await listRes.json()) as Array<{ id: number }> | { items: Array<{ id: number }> };
  const athletes = Array.isArray(raw) ? raw : raw.items;
  const ids = athletes.map((a) => a.id).sort((a, b) => a - b);
  expect(ids.length, 'el seed demo debe tener al menos un atleta').toBeGreaterThan(0);
  for (const id of ids) {
    const anthroRes = await request.get(`${apiBaseUrl()}/api/athletes/${id}/anthropometry`, {
      headers,
    });
    if (!anthroRes.ok()) continue;
    const records = (await anthroRes.json()) as unknown[];
    if (records.length > 0) return id;
  }
  return ids[0];
}

/** Login del coach por la UI (mismo flujo que los specs históricos). */
export async function loginAsCoach(page: Page): Promise<void> {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/**
 * Navega al detalle del atleta demo y espera la respuesta de antropometría
 * para no asertar contra el skeleton de carga.
 */
export async function gotoDemoAthlete(page: Page, tab?: string): Promise<number> {
  const id = await resolveDemoAthleteId(page.request);
  const anthroResponse = page.waitForResponse(
    (r) => new RegExp(`/api/athletes/${id}/anthropometry`).test(r.url()) && r.status() === 200,
    { timeout: 30_000 },
  );
  await page.goto(tab ? `/athletes/${id}?tab=${tab}` : `/athletes/${id}`);
  await expect(page).toHaveURL(new RegExp(`/athletes/${id}`));
  await anthroResponse;
  return id;
}
