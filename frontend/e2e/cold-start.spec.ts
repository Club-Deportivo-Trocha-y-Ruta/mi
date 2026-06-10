/**
 * E2E smoke — feature 012 (perceived performance / cold start).
 *
 * A diferencia del resto de specs e2e, NO requiere backend: el escenario bajo
 * prueba es justamente un backend dormido/inalcanzable, así que se simula con
 * route mocking de Playwright.
 *
 * Cubre (tasks.md T022):
 *   1. Warm-up: GET /health se dispara al montar /login.
 *   2. Banner "la aplicación está iniciando…" aparece tras ≥3 s de espera y
 *      se limpia solo cuando llega la respuesta.
 *   3. Persistencia: tras visitar /competitions con sesión mockeada, una
 *      recarga con la red caída sigue mostrando la lista (restaurada del
 *      snapshot en localStorage).
 */
import { test, expect, type Page } from "@playwright/test";

const TOKENS = {
  access_token: "e2e-access",
  refresh_token: "e2e-refresh",
  token_type: "bearer",
};

const ME = {
  id: 99,
  email: "entrenador@trochyruta.com",
  first_name: "Juan",
  last_name: "Diaz",
  role: "coach",
  is_active: true,
  can_login: true,
  created_at: "2026-01-01T00:00:00Z",
};

const RACE_EVENTS = {
  items: [
    {
      id: 1,
      series_id: 1,
      sequence_number: 3,
      name: "Copa Valle III — La Cumbre",
      event_date: "2026-04-19",
      location: "La Cumbre",
      is_championship: false,
      status: "planned",
      has_results: false,
      has_calendar_event: true,
      conditions_completeness: "partial",
    },
  ],
  total: 1,
};

/** Mockea login + me + listas mínimas para llegar autenticado a /competitions. */
async function mockAuthenticatedApi(page: Page): Promise<void> {
  await page.route("**/api/auth/login", (route) =>
    route.fulfill({ json: TOKENS }),
  );
  await page.route("**/api/auth/me", (route) => route.fulfill({ json: ME }));
  await page.route("**/api/race-analysis/race-events/?**", (route) =>
    route.fulfill({ json: RACE_EVENTS }),
  );
  await page.route("**/api/race-analysis/race-events/", (route) =>
    route.fulfill({ json: RACE_EVENTS }),
  );
  // Resto de APIs (dashboard, etc.): respuestas vacías inofensivas.
  await page.route("**/api/athletes**", (route) =>
    route.fulfill({ json: { items: [], total: 0 } }),
  );
  await page.route("**/health", (route) => route.fulfill({ json: { ok: true } }));
}

async function loginAsCoach(page: Page): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(ME.email);
  await page.getByRole("textbox", { name: /contraseña/i }).fill("Coach2026!");
  await page.getByRole("button", { name: /ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

// E2E-012-1 — warm-up ping al montar el login
test("E2E-012-1: GET /health se dispara al montar la página de login", async ({
  page,
}) => {
  let healthPinged = false;
  await page.route("**/health", (route) => {
    healthPinged = true;
    return route.fulfill({ json: { ok: true } });
  });

  await page.goto("/login");
  await expect.poll(() => healthPinged, { timeout: 5_000 }).toBe(true);
});

// E2E-012-2 — banner de arranque tras ≥3 s, se limpia con la respuesta
test("E2E-012-2: espera >3 s muestra el banner de arranque y la respuesta lo limpia", async ({
  page,
}) => {
  await page.route("**/health", (route) => route.fulfill({ json: { ok: true } }));
  // Login tarda ~4.5 s (simula cold start) y luego falla con 401: el banner
  // debe aparecer durante la espera y desaparecer al llegar la respuesta.
  await page.route("**/api/auth/login", async (route) => {
    await new Promise((r) => setTimeout(r, 4_500));
    await route.fulfill({
      status: 401,
      json: { detail: "Credenciales inválidas" },
    });
  });

  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(ME.email);
  await page.getByRole("textbox", { name: /contraseña/i }).fill("Coach2026!");
  await page.getByRole("button", { name: /ingresar/i }).click();

  const banner = page.getByRole("status");
  // No aparece de inmediato (umbral 3 s)…
  await page.waitForTimeout(1_000);
  await expect(banner).toHaveCount(0);
  // …aparece pasado el umbral…
  await expect(banner).toContainText(/la aplicación está iniciando/i, {
    timeout: 4_000,
  });
  // …y se limpia sola cuando la respuesta llega (sin acción del usuario).
  await expect(banner).toHaveCount(0, { timeout: 4_000 });
  await expect(page.getByText(/credenciales inválidas/i)).toBeVisible();
});

// E2E-012-3 — recarga con red caída renderiza la lista desde el snapshot
test("E2E-012-3: /competitions recargada sin red muestra la lista persistida", async ({
  page,
}) => {
  await mockAuthenticatedApi(page);
  await loginAsCoach(page);

  await page.goto("/competitions");
  await expect(page.getByText("Copa Valle III — La Cumbre")).toBeVisible();

  // Deja que el persister haga throttle-flush a localStorage (1 s).
  await page.waitForTimeout(1_500);
  const snapshot = await page.evaluate(() =>
    localStorage.getItem("tyr:rq-cache:v1"),
  );
  expect(snapshot).not.toBeNull();
  expect(snapshot).toContain("Copa Valle III");

  // Red caída: TODO el API aborta (backend dormido/inalcanzable).
  await page.unrouteAll({ behavior: "ignoreErrors" });
  await page.route("**/api/**", (route) => route.abort("connectionrefused"));
  await page.route("**/health", (route) => route.abort("connectionrefused"));

  await page.reload();
  // La lista se restaura del snapshot — visible sin esperar al servidor.
  await expect(page.getByText("Copa Valle III — La Cumbre")).toBeVisible({
    timeout: 5_000,
  });
});
