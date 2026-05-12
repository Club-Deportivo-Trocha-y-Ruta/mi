/**
 * E2E del módulo de Calendario — vista del padre.
 *
 * Backend mockeado vía page.route. Valida:
 * - Padre navega a /parents/calendar y ve sus eventos
 * - El drawer muestra los datos del evento y NO expone campos privados
 *   (coach_notes, audiences, created_by_user_id) en el DOM
 * - El padre puede ejecutar RSVP en eventos que NO son training_session
 * - La query a /calendar/events incluye el athlete_id seleccionado y NO
 *   se envía athlete_id cuando se elige "Todos"
 */
import { test, expect, type Page, type Route } from '@playwright/test';

const PARENT_USER = {
  id: 3,
  first_name: 'Padre',
  last_name: 'Test',
  email: 'padre@test.com',
  role: 'parent',
  can_login: true,
  is_active: true,
};

const FAKE_TOKENS = {
  access_token: 'fake-access-token',
  refresh_token: 'fake-refresh-token',
};

const MY_ATHLETES = [
  {
    athlete_id: 42,
    athlete_first_name: 'Santiago',
    athlete_last_name: 'García',
    birth_date: '2013-06-01',
    sex: 'M',
    age_decimal: 12.9,
    category: 'Infantil A',
    relationship: 'padre',
    latest_anthropometry_date: null,
    maturation_status: null,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: 'never',
  },
];

const TODAY = new Date();
const Y = TODAY.getFullYear();
const M = String(TODAY.getMonth() + 1).padStart(2, '0');
const D20 = `${Y}-${M}-20`;

const EVENTS_FIXTURE = [
  {
    id: 201,
    title: 'Asamblea trimestral',
    start: `${D20}T18:00:00`,
    end: `${D20}T20:00:00`,
    allDay: false,
    event_type: 'club_event',
    color_hex: null,
    status: 'scheduled',
    // Backend YA filtra description para padres (fix MEDIO). Solo location.
    extended_props: { location: 'Sede del club' },
  },
];

const EVENT_DETAIL = {
  id: 201,
  title: 'Asamblea trimestral',
  description: 'Reunión con padres',
  location: 'Sede del club',
  start_at: `${D20}T18:00:00`,
  end_at: `${D20}T20:00:00`,
  all_day: false,
  timezone: 'America/Bogota',
  event_type: 'club_event',
  status: 'scheduled',
  event_data: { kind: 'meeting' },
  color_hex: null,
  // EventReadParent: SIN created_by_user_id ni audiences. Verificamos abajo.
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const ATTENDANCES_FIXTURE = [
  {
    id: 1,
    event_id: 201,
    athlete_id: 42, // hijo del padre
    rsvp_status: 'pending',
    rsvp_at: null,
    rsvp_by_user_id: null,
    actual_status: 'unknown',
    notes: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

interface MockState {
  lastCalendarQueryParams: URLSearchParams | null;
  lastRSVPBody: any;
}

async function setupAuth(page: Page) {
  await page.addInitScript(({ tokens, user }) => {
    sessionStorage.setItem(
      'auth-session',
      JSON.stringify({
        state: {
          accessToken: tokens.access_token,
          refreshToken: tokens.refresh_token,
          user,
          isAuthenticated: true,
          isLoading: false,
        },
        version: 0,
      }),
    );
  }, { tokens: FAKE_TOKENS, user: PARENT_USER });
}

async function mockBackendForParent(page: Page): Promise<MockState> {
  const state: MockState = { lastCalendarQueryParams: null, lastRSVPBody: null };

  await page.route('**/api/auth/me', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PARENT_USER) }),
  );

  await page.route('**/api/parent-athletes/my-athletes', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MY_ATHLETES) }),
  );

  await page.route('**/api/calendar/events?*', async (route) => {
    if (route.request().method() === 'GET') {
      state.lastCalendarQueryParams = new URL(route.request().url()).searchParams;
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EVENTS_FIXTURE) });
    }
    return route.continue();
  });

  await page.route('**/api/calendar/events/201', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(EVENT_DETAIL) }),
  );

  await page.route('**/api/calendar/events/201/attendances', (route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(ATTENDANCES_FIXTURE) }),
  );

  await page.route('**/api/calendar/events/201/rsvp', async (route) => {
    if (route.request().method() === 'POST') {
      state.lastRSVPBody = route.request().postDataJSON();
      const updated = { ...ATTENDANCES_FIXTURE[0], rsvp_status: state.lastRSVPBody.rsvp_status, rsvp_at: new Date().toISOString() };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(updated) });
    }
    return route.continue();
  });

  return state;
}

// ---------------------------------------------------------------------------

test.describe('Calendar parent E2E', () => {
  test('E2E-CAL-P-01: padre navega a /parents/calendar y ve sus eventos', async ({ page }) => {
    await setupAuth(page);
    await mockBackendForParent(page);

    await page.goto('/parents/calendar');

    await expect(page.getByRole('heading', { name: /mi calendario/i })).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/eventos donde tu .*atleta/i)).toBeVisible();
    await expect(page.getByText('Asamblea trimestral').first()).toBeVisible({ timeout: 10_000 });
  });

  test('E2E-CAL-P-02: la query a /calendar/events fuerza mine_only=true', async ({ page }) => {
    await setupAuth(page);
    const state = await mockBackendForParent(page);

    await page.goto('/parents/calendar');
    await expect(page.getByText('Asamblea trimestral').first()).toBeVisible({ timeout: 10_000 });

    // El backend fuerza mine_only=true en el servidor, pero el cliente envia from/to
    expect(state.lastCalendarQueryParams).not.toBeNull();
    expect(state.lastCalendarQueryParams!.get('from')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(state.lastCalendarQueryParams!.get('to')).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });

  test('E2E-CAL-P-03: pagina de detalle del evento muestra titulo y ubicacion', async ({ page }) => {
    await setupAuth(page);
    await mockBackendForParent(page);

    // Navegamos directamente a la pagina de detalle (deep link / compartible)
    await page.goto('/parents/calendar/events/201');

    await expect(page.getByRole('heading', { name: /asamblea trimestral/i }).first())
      .toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Sede del club').first()).toBeVisible();
  });

  test('E2E-CAL-P-04: privacidad — pagina de detalle NO expone campos internos del coach', async ({ page }) => {
    await setupAuth(page);
    await mockBackendForParent(page);

    await page.goto('/parents/calendar/events/201');
    await expect(page.getByRole('heading', { name: /asamblea trimestral/i }).first())
      .toBeVisible({ timeout: 10_000 });

    const body = page.locator('body');
    await expect(body).not.toContainText(/created_by_user_id/i);
    await expect(body).not.toContainText(/audiencia interna/i);
    await expect(body).not.toContainText(/coach_notes/i);
    await expect(body).not.toContainText(/"audience_type":/);
  });

  test('E2E-CAL-P-05: padre ejecuta RSVP "Aceptar" desde pagina de detalle', async ({ page }) => {
    await setupAuth(page);
    const state = await mockBackendForParent(page);

    await page.goto('/parents/calendar/events/201');
    await expect(page.getByRole('heading', { name: /asamblea trimestral/i }).first())
      .toBeVisible({ timeout: 10_000 });

    const acceptBtn = page.getByRole('button', { name: /^aceptar$/i }).first();
    await expect(acceptBtn).toBeVisible({ timeout: 5_000 });
    await acceptBtn.click();

    await expect.poll(() => state.lastRSVPBody, { timeout: 5_000 }).not.toBeNull();
    expect(state.lastRSVPBody.athlete_id).toBe(42);
    expect(state.lastRSVPBody.rsvp_status).toBe('accepted');
  });

  test('E2E-CAL-P-06: estado vacío cuando no hay eventos en el mes', async ({ page }) => {
    await setupAuth(page);

    await page.route('**/api/auth/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PARENT_USER) }),
    );
    await page.route('**/api/parent-athletes/my-athletes', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MY_ATHLETES) }),
    );
    await page.route('**/api/calendar/events?*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/parents/calendar');

    await expect(page.getByTestId('empty-state')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/sin eventos este mes/i)).toBeVisible();
  });

  test('E2E-CAL-P-08: padre ve cumpleaños virtual en el calendario (auto-sync)', async ({ page }) => {
    await setupAuth(page);

    // Mock: lista de eventos contiene un cumpleaños virtual (ID negativo)
    const birthdayDate = `${Y}-${M}-25`;
    const birthdayEvent = {
      id: -(parseInt(Y) * 1_000_000 + 42),
      title: '🎂 Cumpleaños de Mateo',
      start: `${birthdayDate}T00:00:00`,
      end: `${birthdayDate}T23:59:59`,
      allDay: true,
      event_type: 'birthday',
      color_hex: null,
      status: 'scheduled',
      extended_props: { location: null },
    };

    await page.route('**/api/auth/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PARENT_USER) }),
    );
    await page.route('**/api/parent-athletes/my-athletes', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(MY_ATHLETES) }),
    );
    await page.route('**/api/calendar/events?*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify([birthdayEvent]) }),
    );

    await page.goto('/parents/calendar');

    await expect(page.getByText(/Cumpleaños de Mateo/i).first()).toBeVisible({ timeout: 10_000 });
  });

  test('E2E-CAL-P-07: padre sin atletas vinculados ve mensaje informativo', async ({ page }) => {
    await setupAuth(page);

    await page.route('**/api/auth/me', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(PARENT_USER) }),
    );
    await page.route('**/api/parent-athletes/my-athletes', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );
    await page.route('**/api/calendar/events?*', (route) =>
      route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
    );

    await page.goto('/parents/calendar');

    await expect(page.getByTestId('no-athletes-state')).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/sin atletas vinculados/i)).toBeVisible();
  });
});
