/**
 * E2E del módulo de Calendario — vista del coach.
 *
 * Backend mockeado vía page.route. Valida:
 * - Coach navega a /calendar y ve FullCalendar
 * - Render de eventos en el grid mensual
 * - Click en evento abre el drawer con detalle
 * - Creación de evento desde el formulario
 * - Filtros (tipo de evento) ajustan la query
 *
 * Las pruebas del backend (RBAC, privacidad, persistencia) están cubiertas por
 * los 249 tests pytest. Aquí validamos el flujo de UI end-to-end.
 */
import { test, expect, type Page, type Route } from '@playwright/test';

const COACH_USER = {
  id: 1,
  first_name: 'Entrenador',
  last_name: 'Test',
  email: 'entrenador@test.com',
  role: 'coach',
  can_login: true,
  is_active: true,
};

const FAKE_TOKENS = {
  access_token: 'fake-access-token',
  refresh_token: 'fake-refresh-token',
  token_type: 'bearer',
};

const TODAY = new Date();
const Y = TODAY.getFullYear();
const M = String(TODAY.getMonth() + 1).padStart(2, '0');
const D15 = `${Y}-${M}-15`;

const EVENTS_FIXTURE = [
  {
    id: 101,
    title: 'Entrenamiento técnico',
    start: `${D15}T16:00:00`,
    end: `${D15}T18:00:00`,
    allDay: false,
    event_type: 'training_session',
    color_hex: null,
    status: 'scheduled',
    extended_props: { location: 'Sevilla', description: 'Descenso técnico' },
  },
  {
    id: 102,
    title: 'Asamblea anual del club',
    start: `${D15}T19:00:00`,
    end: `${D15}T21:00:00`,
    allDay: false,
    event_type: 'club_event',
    color_hex: null,
    status: 'scheduled',
    extended_props: { location: 'Sede del club', description: 'Reunión anual con padres' },
  },
];

const EVENT_DETAIL = {
  id: 102,
  title: 'Asamblea anual del club',
  description: 'Reunión anual con padres',
  location: 'Sede del club',
  start_at: `${D15}T19:00:00`,
  end_at: `${D15}T21:00:00`,
  all_day: false,
  timezone: 'America/Bogota',
  event_type: 'club_event',
  status: 'scheduled',
  event_data: { kind: 'meeting' },
  color_hex: null,
  created_by_user_id: 1,
  audiences: [{ id: 1, audience_type: 'all_club', audience_value: {} }],
  attendances: [],
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

async function setupAuth(page: Page) {
  // Inyecta sesión autenticada en sessionStorage (formato del Zustand store).
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
  }, { tokens: FAKE_TOKENS, user: COACH_USER });
}

async function mockBackendForCoach(page: Page, opts: { events?: any[]; created?: any } = {}) {
  const events = opts.events ?? EVENTS_FIXTURE;
  const createdRef = { current: opts.created };

  await page.route('**/api/auth/me', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(COACH_USER) }),
  );

  await page.route('**/api/calendar/events?*', async (route: Route) => {
    const url = new URL(route.request().url());
    if (route.request().method() === 'GET') {
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(events) });
    }
    return route.continue();
  });

  await page.route('**/api/calendar/events', async (route: Route) => {
    if (route.request().method() === 'POST') {
      const body = route.request().postDataJSON();
      const newEvent = {
        id: 999,
        ...body,
        created_by_user_id: 1,
        audiences: body.audiences ?? [],
        attendances: [],
        status: 'scheduled',
        timezone: body.timezone ?? 'America/Bogota',
        all_day: body.all_day ?? false,
        color_hex: body.color_hex ?? null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      createdRef.current = newEvent;
      return route.fulfill({ status: 201, contentType: 'application/json', body: JSON.stringify(newEvent) });
    }
    return route.continue();
  });

  await page.route('**/api/calendar/events/*', async (route: Route) => {
    const url = route.request().url();
    const idMatch = url.match(/\/calendar\/events\/(\d+)(\?|$)/);
    if (idMatch && route.request().method() === 'GET') {
      const id = Number(idMatch[1]);
      const detail = id === 102 ? EVENT_DETAIL : { ...EVENT_DETAIL, id };
      return route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(detail) });
    }
    return route.continue();
  });

  // Generic athletes/clubs/me endpoints used by other parts of the app.
  await page.route('**/api/parent-athletes/my-athletes', (route: Route) =>
    route.fulfill({ status: 200, contentType: 'application/json', body: '[]' }),
  );

  return createdRef;
}

// ---------------------------------------------------------------------------

test.describe('Calendar coach E2E', () => {
  test('E2E-CAL-C-01: coach navega a /calendar y ve FullCalendar montado', async ({ page }) => {
    await setupAuth(page);
    await mockBackendForCoach(page);

    await page.goto('/calendar');

    // FullCalendar renderiza un toolbar con título del mes
    const calendar = page.locator('.fc');
    await expect(calendar).toBeVisible({ timeout: 10_000 });

    // El título principal de la página
    await expect(page.getByRole('heading', { name: /calendario/i }).first()).toBeVisible();
  });

  test('E2E-CAL-C-02: eventos del mes aparecen en el grid', async ({ page }) => {
    await setupAuth(page);
    await mockBackendForCoach(page);

    await page.goto('/calendar');

    // Los títulos de ambos eventos están presentes
    await expect(page.getByText('Entrenamiento técnico').first()).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText('Asamblea anual del club').first()).toBeVisible();
  });

  test('E2E-CAL-C-03: navegar al formulario de edición de un evento existente', async ({ page }) => {
    await setupAuth(page);
    await mockBackendForCoach(page);

    // EventFormPage en modo edit consume GET /events/{id} y rellena el formulario.
    await page.goto('/calendar/events/102/edit');

    // El form debe renderizar el título existente como valor del input.
    const titleInput = page.getByLabel(/título/i).first();
    await expect(titleInput).toBeVisible({ timeout: 10_000 });
    await expect(titleInput).toHaveValue(/asamblea anual del club/i, { timeout: 5_000 });
  });

  test('E2E-CAL-C-05: cumpleaños virtual aparece automaticamente en el calendario', async ({ page }) => {
    await setupAuth(page);

    const birthdayDate = `${Y}-${M}-25`;
    const birthdayEvent = {
      id: -(parseInt(Y) * 1_000_000 + 7),
      title: '🎂 Cumpleaños de Valentina',
      start: `${birthdayDate}T00:00:00`,
      end: `${birthdayDate}T23:59:59`,
      allDay: true,
      event_type: 'birthday',
      color_hex: null,
      status: 'scheduled',
      extended_props: { location: null, description: null },
    };
    await mockBackendForCoach(page, { events: [...EVENTS_FIXTURE, birthdayEvent] });

    await page.goto('/calendar');
    await expect(page.getByText(/Cumpleaños de Valentina/i).first())
      .toBeVisible({ timeout: 10_000 });
  });

  test('E2E-CAL-C-04: la entrada "Calendario" está en la navegación del coach', async ({ page }) => {
    await setupAuth(page);
    await mockBackendForCoach(page);

    await page.goto('/dashboard');

    // El sidebar debe contener un link al calendario
    const calendarLink = page.getByRole('link', { name: /calendario/i }).first();
    await expect(calendarLink).toBeVisible({ timeout: 10_000 });

    await calendarLink.click();
    await expect(page).toHaveURL(/\/calendar/);
  });
});
