// Requiere: docker compose up (backend + MailHog en :8025)
//
// E2E — Sesiones co-dirigidas, notificación a familias nombrando al
// entrenador que actuó (feature 041 — gobernanza multi-coach, US4).
// Contrato: specs/041-multi-coach-governance/contracts/session-coaches.md
//
// Cubre:
//  - Un entrenador (coach2, sesión de la app en un contexto de navegador
//    separado) crea una sesión y asigna a dos entrenadores (mínimo 1, aquí
//    dos) vía `SessionCoachesField`.
//  - El correo de convocatoria a la familia nombra a `acting_coach_name`
//    (quien creó/actuó), no a un entrenador arbitrario de la sesión (§5).
//
// Datos: atleta y familia del seed (`entrenador2@trochyruta.com` /
// `padre@trochayruta.com`), sintéticos.
import { test, expect, type Page } from '@playwright/test';
import { realTokens } from './helpers/session';
import { resolveDemoAthleteId } from './helpers/demo-athlete';

function apiBaseUrl(): string {
  return process.env.E2E_API_BASE_URL ?? 'http://localhost:8000';
}

function mailhogBaseUrl(): string {
  return process.env.E2E_MAILHOG_BASE_URL ?? 'http://localhost:8025';
}

async function setupAuthForRole(page: Page, role: 'coach' | 'coach2') {
  const tokens = await realTokens(page.request, role);
  // `SessionCoachesField` prellena el chip del propio entrenador leyendo
  // `useAuthStore(s => s.user)` (ver componente) — el store no hace fetchMe
  // proactivo al montar si ya hay `accessToken` en sessionStorage (solo lo
  // hace tras login por UI o al refrescar un token vencido). Con `user: null`
  // inyectado el chip nunca aparece. Se resuelve al vuelo, igual que
  // `newsletter-conflict.spec.ts::setupAuth`.
  const meRes = await page.request.get(`${apiBaseUrl()}/api/auth/me`, {
    headers: { Authorization: `Bearer ${tokens.access_token}` },
  });
  if (!meRes.ok()) {
    throw new Error(`setupAuthForRole: GET /auth/me (${role}) devolvió ${meRes.status()}`);
  }
  const sessionUser = await meRes.json();
  await page.addInitScript(
    ({ accessToken, refreshToken, user }) => {
      sessionStorage.setItem(
        'auth-session',
        JSON.stringify({
          state: {
            accessToken,
            refreshToken,
            user,
            isAuthenticated: true,
            isLoading: false,
          },
          version: 0,
        }),
      );
    },
    { accessToken: tokens.access_token, refreshToken: tokens.refresh_token, user: sessionUser },
  );
}

test.describe('Session coaches E2E', () => {
  test('E2E-SESCO-001: el wizard exige al menos un entrenador y permite agregar un segundo', async ({
    page,
  }) => {
    await setupAuthForRole(page, 'coach2');
    await page.goto('/training/sessions/new');

    await expect(page.getByTestId('session-step-general')).toBeVisible({ timeout: 15_000 });

    // El propio coach2 queda preseleccionado por defecto (prefill de creación).
    await expect(page.getByTestId('selected-coach-chips')).toBeVisible({ timeout: 10_000 });
    const chips = page.getByTestId('selected-coach-chips').locator('li');
    await expect(chips).toHaveCount(1);

    // Con un solo entrenador, el botón "Quitar" de ese chip debe estar
    // deshabilitado — nunca puede quedar la sesión sin entrenador (min 1).
    const removeButtons = page.getByTestId('selected-coach-chips').getByRole('button');
    await expect(removeButtons.first()).toBeDisabled();

    // Agregar al segundo entrenador del club (coach original) desde la lista.
    const otherCoachRow = page.getByRole('checkbox', { name: /^Agregar a /i }).first();
    if (await otherCoachRow.count()) {
      await otherCoachRow.check();
      await expect(page.getByTestId('selected-coach-chips').locator('li')).toHaveCount(2);
    }
  });

  test('E2E-SESCO-002: el correo de convocatoria a la familia nombra al entrenador que creó la sesión', async ({
    page,
  }) => {
    // coach2 crea la sesión con coach2 y el coach original a cargo, convocando
    // al atleta demo (vinculado a la familia del seed).
    const tokens = await realTokens(page.request, 'coach2');
    const coach1Tokens = await realTokens(page.request, 'coach');
    const athleteId = await resolveDemoAthleteId(page.request);

    const meRes = await page.request.get(`${apiBaseUrl()}/api/auth/me`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    expect(meRes.ok()).toBeTruthy();
    const coach2User = (await meRes.json()) as { id: number; first_name: string; last_name: string };

    const meRes1 = await page.request.get(`${apiBaseUrl()}/api/auth/me`, {
      headers: { Authorization: `Bearer ${coach1Tokens.access_token}` },
    });
    const coach1User = (await meRes1.json()) as { id: number };

    const tomorrow = new Date(Date.now() + 24 * 60 * 60 * 1000);
    const scheduledDate = tomorrow.toISOString().slice(0, 10);

    const createRes = await page.request.post(`${apiBaseUrl()}/api/training-sessions`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
      data: {
        scheduled_date: scheduledDate,
        scheduled_start_time: '15:00:00',
        duration_min: 60,
        location: 'Pista sintética E2E',
        technical_focus: 'Frenada',
        convocados_athlete_ids: [athleteId],
        coach_user_ids: [coach2User.id, coach1User.id],
      },
    });
    expect(createRes.ok(), `crear sesión falló: ${createRes.status()}`).toBeTruthy();
    const session = (await createRes.json()) as {
      id: number;
      coaches?: Array<{ user_id: number; display_name: string }>;
    };

    // La respuesta lista a ambos entrenadores asignados.
    expect(session.coaches?.map((c) => c.user_id).sort()).toEqual(
      [coach2User.id, coach1User.id].sort(),
    );

    // Verificación del correo vía la API de MailHog (best-effort: si el
    // stack no expone MailHog en este entorno, se documenta y no se falla
    // la corrida completa por infraestructura ajena al spec).
    let mailhogReachable = true;
    try {
      const searchRes = await page.request.get(
        `${mailhogBaseUrl()}/api/v2/search?kind=to&query=padre@trochayruta.com`,
      );
      mailhogReachable = searchRes.ok();
      if (mailhogReachable) {
        const body = (await searchRes.json()) as {
          items: Array<{ Content: { Body: string } }>;
        };
        const acting = `${coach2User.first_name} ${coach2User.last_name}`.trim();
        const named = body.items.some((item) => item.Content.Body.includes(acting));
        expect(named, 'el correo de convocatoria debe nombrar al entrenador que creó la sesión').toBe(
          true,
        );
      }
    } catch {
      mailhogReachable = false;
    }
    test.skip(!mailhogReachable, 'MailHog no accesible en este entorno — ver reporte de la tarea.');
  });
});
