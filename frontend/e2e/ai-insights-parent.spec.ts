/**
 * E2E — feature 036, Wave 5 (T072), migrado a la pestaña única «Carreras» por
 * la feature 045 (T064): la vista del padre/madre es una vista de privacidad,
 * no solo un layout distinto.
 *
 * Motivación (spec.md, User Story 7 de la 036; FR-015 de la 045): la pestaña
 * «Carreras» del coach tiene 3 vistas (Progresión, Análisis IA, Comparar) y
 * la del padre solo 2 (Progresión, Análisis IA) — esa asimetría es
 * intencional: `CarrerasTab` con `audience="family"` no monta «Comparar»
 * (distribución del campo + comparador), ni el lanzador, el chat, las casillas
 * de boletín, ni las métricas contra el líder/podio («Brecha vs. 1.ª
 * posición», «Brecha vs. podio» son solo-coach). Esta spec no se conforma con
 * "no se ve" (podría estar oculto con CSS): verifica AUSENCIA del DOM y,
 * como refuerzo, que el backend jamás recibe una petición a los endpoints
 * exclusivos de coach — si un regresión futura volviera a montar esos
 * sub-componentes para un padre, esta spec debe fallar por las dos vías.
 *
 * Direcciones (contracts/ui-routes.md): `?tab=races[&view=progresion|analisis]`;
 * el alias `?tab=ai-analysis` redirige a `?tab=races&view=analisis`, y
 * `?view=comparar` cae en «Progresión» sin error (vista solo-coach).
 *
 * Incluye además el otro borde de la misma invariante de privacidad: un
 * padre que edita la URL para ver el análisis de un atleta que NO es su
 * hijo debe toparse con el 403 del backend sin que nada de ese atleta
 * llegue a pintarse.
 *
 * Sin backend real — Playwright intercepta cada request con `page.route()`
 * usando predicados de URL (nunca globs, ver `e2e/cold-start.spec.ts`).
 *
 * Privacidad: todo nombre de atleta/madre/padre en este archivo es
 * sintético (Ley 1581 — estos fixtures quedan commiteados en git).
 */
import { test, expect, type Page } from "@playwright/test";
import { realTokens } from './helpers/session';
import { mockAthleteRaceHistory } from './helpers/race-history';

// ---------------------------------------------------------------------------
// Fixtures — sintéticos, nunca nombres reales (Ley 1581)
// ---------------------------------------------------------------------------

const SEASON = new Date().getFullYear();

const TOKENS = {
  access_token: "e2e-parent-access",
  refresh_token: "e2e-parent-refresh",
  token_type: "bearer",
};

const PARENT = {
  id: 801,
  email: "madre.prueba@trochyruta.com",
  first_name: "Madre",
  last_name: "Sintetica",
  phone: null,
  role: "parent",
  is_active: true,
  can_login: true,
  club_ids: [1],
  created_at: "2026-01-01T00:00:00Z",
};

const CHILD_ID = 4601;
const OTHER_CHILD_ID = 4602;

const CHILD = {
  id: CHILD_ID,
  user_id: 9601,
  first_name: "Hija",
  last_name: "Sintetica",
  birth_date: "2013-05-04",
  sex: "F",
  club_join_date: "2024-02-01",
  years_in_club: 2,
  age_decimal: 13.2,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-02-01T00:00:00Z",
  latest_anthropometry: null,
};

const MY_ATHLETES = [
  {
    athlete_id: CHILD_ID,
    athlete_first_name: CHILD.first_name,
    athlete_last_name: CHILD.last_name,
    birth_date: CHILD.birth_date,
    sex: CHILD.sex,
    age_decimal: CHILD.age_decimal,
    category: CHILD.category,
    relationship: "madre",
    latest_anthropometry_date: null,
    maturation_status: null,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  },
];

// Insight distintivo del propio hijo — debe verse.
const OWN_CHILD_INSIGHT = {
  id: 7901,
  season: SEASON,
  valida_num: 1,
  event_id: 9701,
  event_date: `${SEASON}-03-15`,
  series_kind: "cup",
  use_case: "race_analysis",
  summary_text:
    "Marcador sintético E2E-PARENT-OWN: mejoró la salida y mantuvo el grupo de cabeza.",
  confidence: "high",
  model: "gemini-3.1-flash-lite",
  prompt_version: "race_analyst_v1",
  coach_approved: true,
  generated_at: `${SEASON}-03-15T10:00:00Z`,
  approved_at: `${SEASON}-03-15T12:00:00Z`,
  is_active: true,
  deprecated_at: null,
  is_fallback: false,
};

const FALLBACK_INSIGHT = {
  ...OWN_CHILD_INSIGHT,
  id: 7902,
  valida_num: 2,
  event_id: 9702,
  event_date: `${SEASON}-04-12`,
  prompt_version: "race_analyst_v2",
  confidence: "low",
  summary_text:
    "Análisis IA no disponible en este momento. Revisa los datos crudos en la sección de resultados.",
  is_fallback: true,
};

// Marcador de un atleta que NO es hijo de este padre — nunca debe verse ni
// pedirse, ni siquiera si el padre edita la URL a mano.
const OTHER_CHILD_MARKER = "MARCADOR-NO-DEBERIA-VERSE-OTRO-ATLETA";

// ---------------------------------------------------------------------------
// Helpers de red — idioma de e2e/cold-start.spec.ts (predicados de URL)
// ---------------------------------------------------------------------------

function isBackend(url: URL): boolean {
  return url.port !== (process.env.E2E_APP_PORT ?? "5173");
}

async function setupAuthParent(page: Page): Promise<void> {
  const liveTokens = await realTokens(page.request, 'parent');
  await page.addInitScript(
    ({ tokens, user }) => {
      sessionStorage.setItem(
        "auth-session",
        JSON.stringify({
          state: {
            accessToken: tokens.access_token,
            refreshToken: tokens.refresh_token,
            user,
            isAuthenticated: true,
          },
          version: 0,
        }),
      );
    },
    { tokens: liveTokens, user: PARENT },
  );
}

/**
 * Mocks base del portal de padres + del propio hijo. Además instala una RED
 * DE SEGURIDAD sobre los endpoints exclusivos de coach (Distribución,
 * lanzar análisis, carreras del picker, resumen de temporada, adjuntar al
 * boletín): si alguno llegara a dispararse, se registra en
 * `coachOnlyHit` en vez de dejar la petición sin mockear (lo que colgaría
 * el test contra un puerto sin backend real).
 */
async function mockCommon(
  page: Page,
): Promise<{ coachOnlyHit: () => string | null }> {
  let hit: string | null = null;

  await page.route(
    (url) => isBackend(url) && url.pathname === "/health",
    (route) => route.fulfill({ json: { ok: true } }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/auth/me",
    (route) => route.fulfill({ json: PARENT }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/parent-athletes/my-athletes",
    (route) => route.fulfill({ json: MY_ATHLETES }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/athletes/${CHILD_ID}`,
    (route) => route.fulfill({ json: CHILD }),
  );
  await page.route(
    (url) =>
      isBackend(url) && url.pathname === `/api/athletes/${CHILD_ID}/anthropometry`,
    (route) => route.fulfill({ json: [] }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/athletes/${CHILD_ID}/activities`,
    (route) =>
      route.fulfill({ json: { items: [], total: 0, page: 1, page_size: 10 } }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${CHILD_ID}/race-analysis/insights`,
    (route) =>
      route.fulfill({
        json: {
          items: [OWN_CHILD_INSIGHT, FALLBACK_INSIGHT],
          total: 2,
          limit: 50,
          offset: 0,
        },
      }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${CHILD_ID}/race-analysis/evolution`,
    (route) =>
      route.fulfill({
        json: { season: SEASON, metric: "ranking", series: [], confidence: "low" },
      }),
  );

  // --- Red de seguridad: endpoints exclusivos de coach --------------------
  const coachOnlyPredicate = (url: URL) =>
    isBackend(url) &&
    (url.pathname === `/api/athletes/${CHILD_ID}/race-analysis/distribution` ||
      url.pathname === `/api/athletes/${CHILD_ID}/race-analysis/races` ||
      url.pathname === `/api/athletes/${CHILD_ID}/race-analysis/runs` ||
      url.pathname === `/api/athletes/${CHILD_ID}/race-analysis/season-summary` ||
      url.pathname ===
        `/api/athletes/${CHILD_ID}/monthly-newsletters/attach-insights` ||
      url.pathname === "/api/ai/status");
  await page.route(coachOnlyPredicate, (route) => {
    hit = new URL(route.request().url()).pathname;
    return route.fulfill({ json: { items: [], total: 0 } });
  });

  return { coachOnlyHit: () => hit };
}

/** Mocks de un atleta que NO pertenece a este padre — usados solo por el
 * test que intenta acceder por URL directa. Nunca deben ser consultados
 * salvo por ESE test, y siempre deben negar el acceso (403), igual que el
 * backend real (RBAC padre↔hijo). */
async function mockOtherChildDenied(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/athletes/${OTHER_CHILD_ID}`,
    (route) =>
      route.fulfill({
        status: 403,
        json: { detail: "No tienes acceso a este atleta." },
      }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${OTHER_CHILD_ID}/anthropometry`,
    (route) => route.fulfill({ status: 403, json: { detail: "Prohibido." } }),
  );
  await page.route(
    (url) =>
      isBackend(url) && url.pathname === `/api/athletes/${OTHER_CHILD_ID}/activities`,
    (route) => route.fulfill({ status: 403, json: { detail: "Prohibido." } }),
  );
  // Nunca debería llegar a pedirse, pero si algo cambiara y SÍ se pidiera,
  // que devuelva un marcador reconocible en vez de colgarse.
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${OTHER_CHILD_ID}/race-analysis/insights`,
    (route) =>
      route.fulfill({
        json: {
          items: [{ ...OWN_CHILD_INSIGHT, id: 9999, summary_text: OTHER_CHILD_MARKER }],
          total: 1,
          limit: 50,
          offset: 0,
        },
      }),
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Feature 036 — vista de padre/madre: privacidad, no solo layout (T072)", () => {
  test("PARENT-001: 2 vistas exactas (sin Comparar), sin checkboxes de boletín ni brechas contra líder/podio, datos del propio hijo", async ({
    page,
  }) => {
    const { coachOnlyHit } = await mockCommon(page);
    const requestedHistoryKinds = await mockAthleteRaceHistory(page, CHILD_ID, {
      audience: "family",
    });

    await setupAuthParent(page);
    await page.goto(`/my-athletes/${CHILD_ID}`);

    await page.getByTestId("parent-tab-races").click();
    await expect(page.getByTestId("carreras-tab")).toBeVisible({
      timeout: 15_000,
    });

    // --- Exactamente 2 vistas, nunca 3 --------------------------------------
    const views = page.locator('[data-testid^="carreras-view-"]');
    await expect(views).toHaveCount(2);
    await expect(page.getByTestId("carreras-view-progresion")).toBeVisible();
    await expect(page.getByTestId("carreras-view-analisis")).toBeVisible();
    await expect(page.getByTestId("carreras-view-comparar")).toHaveCount(0);

    // --- «Progresión» (vista por defecto): solo mediana, percentil y posición
    await expect(page.getByTestId("progression-view")).toBeVisible({
      timeout: 15_000,
    });
    await expect.poll(() => requestedHistoryKinds, { timeout: 15_000 }).toContain("all");
    const metricSelect = page.getByTestId("progression-metric-select");
    await expect(metricSelect).toBeVisible({ timeout: 15_000 });
    await expect(metricSelect.locator("option")).toHaveCount(3);
    await expect(metricSelect.locator("option", { hasText: "Brecha vs. mediana" })).toHaveCount(1);
    await expect(metricSelect.locator("option", { hasText: "Percentil" })).toHaveCount(1);
    await expect(metricSelect.locator("option", { hasText: "Posición" })).toHaveCount(1);
    // Ni el líder ni el podio aparecen en NINGÚN lugar de la vista (Ley 1581
    // + salvaguarda 045): ni como opción ni en la tabla ni en el texto.
    await expect(page.getByText(/brecha vs\. (podio|1\.ª posición)/i)).toHaveCount(0);
    await expect(page.getByText(/gap al podio/i)).toHaveCount(0);

    // --- «Análisis IA»: datos del propio hijo, y ningún marcador ajeno ------
    await page.getByTestId("carreras-view-analisis").click();
    await expect(page).toHaveURL(/[?&]view=analisis(&|$)/);
    await expect(page.getByTestId("analysis-view")).toBeVisible({ timeout: 15_000 });
    // La familia siempre ve la etiqueta de revisión humana.
    await expect(page.getByTestId("analysis-ai-label")).toHaveText(
      "Análisis generado con IA y revisado por el entrenador.",
    );
    // Panorama (héroe) y Histórico conviven en la misma vista: el texto del
    // insight aparece en ambos → `.first()` evita el strict-mode.
    await expect(page.getByText(OWN_CHILD_INSIGHT.summary_text).first()).toBeVisible();
    await expect(page.getByText(OTHER_CHILD_MARKER)).toHaveCount(0);

    // --- Sin ningún control de boletín en Panorama --------------------------
    await expect(page.getByTestId("hero-btn-add-newsletter")).toHaveCount(0);

    // --- Sin checkboxes de boletín en Histórico, ni para el insight normal
    //     ni para el fallback ------------------------------------------------
    await expect(page.getByTestId(`insight-card-${OWN_CHILD_INSIGHT.id}`)).toBeVisible();
    await expect(page.locator('[data-testid^="insight-checkbox-"]')).toHaveCount(0);
    // El fallback tampoco ofrece "Reintentar" (acción de coach) al padre.
    await expect(
      page.getByTestId(`insight-retry-${FALLBACK_INSIGHT.id}`),
    ).toHaveCount(0);
    await expect(
      page.getByTestId(`insight-regenerate-${OWN_CHILD_INSIGHT.id}`),
    ).toHaveCount(0);

    // --- Sin herramientas de coach (lanzador + chat) ni barra de boletín ----
    await expect(page.getByTestId("analysis-coach-tools")).toHaveCount(0);
    await expect(page.getByTestId("launch-analysis-form")).toHaveCount(0);
    await expect(page.getByTestId("newsletter-action-bar")).toHaveCount(0);

    // --- El backend nunca vio una petición a un endpoint exclusivo de coach.
    expect(coachOnlyHit()).toBeNull();
  });

  test("PARENT-003: el alias `?tab=ai-analysis` redirige a «Carreras › Análisis IA»; `?view=comparar` cae en «Progresión» sin error", async ({
    page,
  }) => {
    const { coachOnlyHit } = await mockCommon(page);
    await mockAthleteRaceHistory(page, CHILD_ID, { audience: "family" });

    await setupAuthParent(page);

    // --- Alias legado (correos y notificaciones ya enviados) ----------------
    await page.goto(`/my-athletes/${CHILD_ID}?tab=ai-analysis`);
    await expect(page).toHaveURL(
      new RegExp(`/my-athletes/${CHILD_ID}\\?tab=races&view=analisis$`),
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("carreras-view-analisis")).toHaveAttribute(
      "data-state",
      "active",
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("analysis-view")).toBeVisible({ timeout: 15_000 });
    // La pestaña antigua ya no existe.
    await expect(page.getByTestId("parent-tab-ai-analysis")).toHaveCount(0);

    // --- `view=comparar` es solo-coach: para la familia cae en «Progresión» --
    await page.goto(`/my-athletes/${CHILD_ID}?tab=races&view=comparar`);
    await expect(page.getByTestId("carreras-view-progresion")).toHaveAttribute(
      "data-state",
      "active",
      { timeout: 15_000 },
    );
    await expect(page.getByTestId("progression-view")).toBeVisible({ timeout: 15_000 });
    await expect(page.getByTestId("compare-view")).toHaveCount(0);
    await expect(page.getByTestId("comparator-panel")).toHaveCount(0);
    await expect(page.getByTestId("distribution-chart")).toHaveCount(0);
    // Caer en «Progresión» no es un error: ningún alert dentro de la pestaña.
    await expect(page.getByTestId("carreras-tab").getByRole("alert")).toHaveCount(0);

    expect(coachOnlyHit()).toBeNull();
  });

  test("PARENT-002: URL directa a un atleta que no es su hijo termina en 403, nunca en datos ajenos", async ({
    page,
  }) => {
    await mockCommon(page);
    await mockOtherChildDenied(page);

    await setupAuthParent(page);
    await page.goto(`/my-athletes/${OTHER_CHILD_ID}`);

    // El frontend respeta el 403 del backend: no monta la pestaña «Carreras»
    // ni ningún dato de ese atleta. Timeout generoso: el QueryClient global
    // (App.tsx) usa `retry: 3` como NÚMERO — TanStack Query reintenta
    // igual con un 403 (no distingue 4xx de 5xx salvo que `retry` sea una
    // función) con backoff 1s/2s/4s antes de asentar en `isError`.
    await expect(
      page.getByText(/no se pudo cargar la información del atleta/i),
    ).toBeVisible({ timeout: 20_000 });
    await expect(page.getByTestId("carreras-tab")).toHaveCount(0);
    await expect(page.getByText(OTHER_CHILD_MARKER)).toHaveCount(0);
    await expect(page.getByTestId("parent-tab-races")).toHaveCount(0);
  });
});
