/**
 * Tokens reales del stack e2e aislado para specs que inyectan la sesión en
 * `sessionStorage` (`addInitScript`) y mockean parte de la API.
 *
 * Por qué: el shell de la app (badges del sidebar, resumen del dashboard,
 * inbox) pide varios endpoints que esos specs no mockean. Con tokens
 * inventados el backend responde 401, el interceptor intenta `/auth/refresh`,
 * falla y cierra la sesión — la página queda en /login y toda aserción
 * posterior falla. Con tokens reales del seed demo, lo no mockeado responde
 * 200 contra datos sintéticos y los mocks del spec siguen mandando.
 *
 * Credenciales = seed de desarrollo (`backend/scripts/seed.py`), datos
 * sintéticos; el stack `me` con datos reales nunca es objetivo de Playwright.
 */
import type { APIRequestContext } from '@playwright/test';

export type SeedRole = 'coach' | 'admin' | 'parent';

const CREDENTIALS: Record<SeedRole, { email: string; password: string }> = {
  coach: { email: 'entrenador@trochyruta.com', password: 'Coach2026!' },
  admin: { email: 'admin@trochyruta.com', password: 'Admin2026!' },
  parent: { email: 'padre@trochayruta.com', password: 'Parent2026!' },
};

export interface SessionTokens {
  access_token: string;
  refresh_token: string;
}

const cache = new Map<SeedRole, SessionTokens>();

function apiBaseUrl(): string {
  return process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';
}

/** Login por API (una vez por rol y worker) y devuelve los tokens reales. */
export async function realTokens(
  request: APIRequestContext,
  role: SeedRole = 'coach',
): Promise<SessionTokens> {
  const cached = cache.get(role);
  if (cached) return cached;
  const res = await request.post(`${apiBaseUrl()}/api/auth/login`, {
    data: CREDENTIALS[role],
  });
  if (!res.ok()) {
    throw new Error(`realTokens: login ${role} devolvió HTTP ${res.status()} en ${apiBaseUrl()}`);
  }
  const body = (await res.json()) as SessionTokens;
  const tokens = { access_token: body.access_token, refresh_token: body.refresh_token };
  cache.set(role, tokens);
  return tokens;
}
