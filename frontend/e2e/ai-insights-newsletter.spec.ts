/**
 * E2E — feature 036, Wave 5 (T074): barra sticky del boletín, de punta a punta.
 *
 * Motivación (spec.md, User Story 7 / SC-004): "Ningún placeholder de
 * análisis fallido puede llegar al boletín de una familia". Wave 1 cerró DOS
 * rutas por las que un insight `is_fallback=true` podía colarse al boletín:
 *   1. El checkbox por fila en el histórico (`InsightsTimeline.tsx`).
 *   2. El botón propio de `HeroLastInsightCard.tsx` en Panorama — una
 *      segunda ruta que el checkbox por sí solo no cubría.
 * Ninguna suite hoy dispara el envío real y observa a dónde llega — esta
 * spec no se detiene en "la barra dijo éxito": sigue el `newsletter_id`
 * devuelto por el backend hasta la página del boletín para confirmar que
 * es el mismo recurso, con el año/mes/estado correctos.
 *
 * Sin backend real — Playwright intercepta cada request con `page.route()`
 * usando predicados de URL (nunca globs, ver `e2e/cold-start.spec.ts`).
 *
 * Nota de alcance (documentada para quien retome esto): el contrato actual
 * de `GET .../monthly-newsletters/{id}` (`AthleteNewsletterRead`, backend)
 * NUNCA serializa `selected_race_insight_ids` — ese campo solo vive en la
 * fila de BD y en la respuesta síncrona de `POST attach-insights`. Ningún
 * builder de `email_blocks` ni el PDF lo leen tampoco (verificado con grep
 * sobre `backend/app/services`). Es decir: hoy no existe, en producción,
 * una pantalla donde el contenido de los insights adjuntados se vea
 * reflejado — la prueba más fuerte y honesta que se puede hacer contra el
 * contrato real es (a) el payload exacto que viaja en el POST y (b) que el
 * `newsletter_id` que ese POST devuelve es luego un recurso real y
 * navegable con el año/mes/estado correctos. Ver también 'realBugsFound'
 * en el reporte de esta tarea.
 *
 * Privacidad: todo nombre de atleta/coach en este archivo es sintético.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

// ---------------------------------------------------------------------------
// Fixtures — sintéticos, nunca nombres reales (Ley 1581)
// ---------------------------------------------------------------------------

const SEASON = new Date().getFullYear();
const NOW = new Date();
const NL_YEAR = NOW.getFullYear();
const NL_MONTH = NOW.getMonth() + 1;

const TOKENS = {
  access_token: "e2e-newsletter-access",
  refresh_token: "e2e-newsletter-refresh",
  token_type: "bearer",
};

const COACH = {
  id: 701,
  email: "entrenador.boletin@trochyruta.com",
  first_name: "Coach",
  last_name: "Boletin",
  role: "coach",
  is_active: true,
  can_login: true,
  created_at: "2026-01-01T00:00:00Z",
};

const ATHLETE_ID = 4501;

const ATHLETE = {
  id: ATHLETE_ID,
  user_id: 9501,
  first_name: "Deportista",
  last_name: "PruebaBoletin",
  birth_date: "2011-07-22",
  sex: "F",
  club_join_date: "2023-06-01",
  years_in_club: 3,
  age_decimal: 14.9,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-06-01T00:00:00Z",
  latest_anthropometry: null,
};

interface InsightFixture {
  id: number;
  season: number;
  valida_num: number | null;
  event_id: number | null;
  event_date: string | null;
  series_kind: "cup" | "championship" | null;
  use_case: string;
  summary_text: string;
  confidence: "low" | "medium" | "high";
  model: string;
  prompt_version: string;
  coach_approved: boolean;
  generated_at: string;
  approved_at: string | null;
  is_active: boolean;
  deprecated_at: string | null;
  is_fallback: boolean;
}

const FALLBACK_SUMMARY_TEXT =
  "Análisis IA no disponible en este momento. Revisa los datos crudos en la sección de resultados.";

function normalInsight(
  id: number,
  validaNum: number,
  text: string,
): InsightFixture {
  return {
    id,
    season: SEASON,
    valida_num: validaNum,
    event_id: 9600 + validaNum,
    event_date: `${SEASON}-0${Math.min(validaNum, 9)}-10`,
    series_kind: "cup",
    use_case: "race_analysis",
    summary_text: text,
    confidence: "high",
    model: "gemini-3.1-flash-lite",
    prompt_version: "race_analyst_v1",
    coach_approved: true,
    generated_at: `${SEASON}-0${Math.min(validaNum, 9)}-10T10:00:00Z`,
    approved_at: `${SEASON}-0${Math.min(validaNum, 9)}-10T12:00:00Z`,
    is_active: true,
    deprecated_at: null,
    is_fallback: false,
  };
}

function fallbackInsight(id: number, validaNum: number): InsightFixture {
  return {
    id,
    season: SEASON,
    valida_num: validaNum,
    event_id: 9600 + validaNum,
    event_date: `${SEASON}-0${Math.min(validaNum, 9)}-10`,
    series_kind: "cup",
    use_case: "race_analysis",
    summary_text: FALLBACK_SUMMARY_TEXT,
    confidence: "low",
    model: "gemini-3.1-flash-lite",
    prompt_version: "race_analyst_v2",
    coach_approved: true,
    generated_at: `${SEASON}-0${Math.min(validaNum, 9)}-10T10:00:00Z`,
    approved_at: `${SEASON}-0${Math.min(validaNum, 9)}-10T12:00:00Z`,
    is_active: true,
    deprecated_at: null,
    is_fallback: true,
  };
}

// ---------------------------------------------------------------------------
// Helpers de red — idioma de e2e/cold-start.spec.ts (predicados de URL)
// ---------------------------------------------------------------------------

function isBackend(url: URL): boolean {
  return url.port !== "5173";
}

async function setupAuthCoach(page: Page): Promise<void> {
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
    { tokens: TOKENS, user: COACH },
  );
}

/** Mocks comunes a cualquier render del tab Análisis IA en modo coach. */
async function mockCommon(page: Page): Promise<void> {
  await page.route(
    (url) => isBackend(url) && url.pathname === "/health",
    (route) => route.fulfill({ json: { ok: true } }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/auth/me",
    (route) => route.fulfill({ json: COACH }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === `/api/athletes/${ATHLETE_ID}`,
    (route) => route.fulfill({ json: ATHLETE }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${ATHLETE_ID}/anthropometry`,
    (route) => route.fulfill({ json: [] }),
  );
  await page.route(
    (url) => isBackend(url) && url.pathname === "/api/ai/status",
    (route) =>
      route.fulfill({
        json: {
          budget_status: "ok",
          budget_remaining_pct: 80,
          concurrency_available: true,
          est_wait_seconds: 0,
        },
      }),
  );
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${ATHLETE_ID}/race-analysis/evolution`,
    (route) =>
      route.fulfill({
        json: { season: SEASON, metric: "ranking", series: [], confidence: "low" },
      }),
  );
}

async function mockInsightsList(
  page: Page,
  items: InsightFixture[],
): Promise<void> {
  await page.route(
    (url) =>
      isBackend(url) &&
      url.pathname === `/api/athletes/${ATHLETE_ID}/race-analysis/insights`,
    (route) =>
      route.fulfill({ json: { items, total: items.length, limit: 50, offset: 0 } }),
  );
}

async function gotoAiTab(page: Page): Promise<void> {
  await page.goto(`/athletes/${ATHLETE_ID}?tab=ai_analysis`);
  await expect(page.getByTestId("athlete-ai-analysis-tab")).toBeVisible({
    timeout: 15_000,
  });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Feature 036 — barra sticky del boletín, de punta a punta (T074)", () => {
  test("NEWSLETTER-001: selección real → payload exacto → boletín navegable con el mismo id/año/mes", async ({
    page,
  }) => {
    const REAL_A = normalInsight(
      7701,
      1,
      "Mejoró el manejo en curvas cerradas y sostuvo el ritmo en el último tramo.",
    );
    const REAL_B = normalInsight(
      7702,
      2,
      "Consolidó la posición de pedaleo en subida; RPE percibido bajó de 8 a 6.",
    );
    const FALLBACK = fallbackInsight(7703, 3);
    const NEWSLETTER_ID = 88101;

    let attachRequestBody: Record<string, unknown> | null = null;

    await setupAuthCoach(page);
    await mockCommon(page);
    await mockInsightsList(page, [REAL_A, REAL_B, FALLBACK]);

    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname ===
          `/api/athletes/${ATHLETE_ID}/monthly-newsletters/attach-insights`,
      (route: Route) => {
        attachRequestBody = route.request().postDataJSON();
        return route.fulfill({
          json: {
            newsletter_id: NEWSLETTER_ID,
            athlete_id: ATHLETE_ID,
            year: NL_YEAR,
            month: NL_MONTH,
            status: "draft",
            selected_race_insight_ids: (attachRequestBody?.insight_ids as number[]) ?? [],
            created: true,
          },
        });
      },
    );

    await gotoAiTab(page);
    await page.getByTestId("ai-subtab-history").click();

    // La fila fallback NUNCA tiene checkbox — la única forma de seleccionarla
    // para el boletín simplemente no existe en el DOM.
    await expect(page.getByTestId(`insight-checkbox-${FALLBACK.id}`)).toHaveCount(0);
    await expect(
      page.getByTestId(`insight-fallback-badge-${FALLBACK.id}`),
    ).toBeVisible();
    await expect(page.getByTestId(`insight-retry-${FALLBACK.id}`)).toBeVisible();

    // Selección real de las dos filas con análisis real (click, no estado sintético).
    await expect(page.getByTestId(`insight-checkbox-${REAL_A.id}`)).toBeVisible();
    await page.getByTestId(`insight-checkbox-${REAL_A.id}`).check();
    await page.getByTestId(`insight-checkbox-${REAL_B.id}`).check();

    const bar = page.getByTestId("newsletter-action-bar");
    await expect(bar).toBeVisible();
    await expect(bar).toContainText("2 insights seleccionados");

    await page.getByTestId("newsletter-action-bar-submit").click();

    // Petición real: exactamente los 2 ids reales, nunca el fallback.
    await expect
      .poll(() => attachRequestBody, { timeout: 10_000 })
      .toMatchObject({ insight_ids: [REAL_A.id, REAL_B.id] });
    expect(
      (attachRequestBody as unknown as { insight_ids: number[] } | null)?.insight_ids ?? [],
    ).not.toContain(FALLBACK.id);

    await expect(page.getByTestId("newsletter-action-bar-success")).toBeVisible();
    await expect(bar).toContainText("Agregados al boletín del mes");
    // T013 (comentario en AthleteAIAnalysisTab.tsx): la confirmación se
    // limpia sola a los 3 s — la barra debe desaparecer del todo, no
    // quedarse pegada mostrando "éxito" para siempre.
    await expect(bar).toHaveCount(0, { timeout: 6_000 });

    // No basta con "la barra dijo éxito": seguimos el newsletter_id real
    // hasta la página del boletín y confirmamos que es EL MISMO recurso.
    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname ===
          `/api/athletes/${ATHLETE_ID}/monthly-newsletters/${NEWSLETTER_ID}`,
      (route) =>
        route.fulfill({
          json: {
            id: NEWSLETTER_ID,
            athlete_id: ATHLETE_ID,
            year: NL_YEAR,
            month: NL_MONTH,
            status: "draft",
            email_blocks: {},
            ai_narrative: {
              strengths: "Buen manejo técnico en trazado sinuoso.",
              area_to_develop: "Consistencia de cadencia en subidas largas.",
              milestone: "Primer podio de la temporada.",
              model: "gemini-3.1-flash-lite",
              prompt_version: "monthly_v3",
              confidence: "medium",
            },
            coach_narrative_overrides: null,
            badges_earned: [],
            has_pdf: false,
            pdf_generated_at: null,
            pdf_sha256: null,
            generated_by_user_id: COACH.id,
            approved_by_user_id: null,
            approved_at: null,
            sent_at: null,
            error_message: null,
            created_at: NOW.toISOString(),
            updated_at: NOW.toISOString(),
          },
        }),
    );

    await page.goto(`/training/athlete-newsletters/${ATHLETE_ID}/${NEWSLETTER_ID}`);
    const monthNames = [
      "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
      "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    ];
    await expect(
      page.getByRole("heading", {
        name: new RegExp(`Boletín de ${monthNames[NL_MONTH - 1]} ${NL_YEAR}`, "i"),
      }),
    ).toBeVisible({ timeout: 10_000 });
    await expect(page.getByText(/Borrador/i).first()).toBeVisible();
  });

  test("NEWSLETTER-002: un insight fallback no se puede enviar a la familia por ninguna ruta", async ({
    page,
  }) => {
    // Es el ÚNICO insight (y por lo tanto el "último análisis" que ve el
    // Hero de Panorama) — cubre la segunda ruta que Wave 1 cerró en
    // `HeroLastInsightCard.tsx`, no solo el checkbox del histórico.
    const FALLBACK_ONLY = fallbackInsight(7801, 1);

    await setupAuthCoach(page);
    await mockCommon(page);
    await mockInsightsList(page, [FALLBACK_ONLY]);

    // Red de seguridad: si CUALQUIER ruta de la UI lograra intentar
    // adjuntar este insight al boletín, que quede registrado (y que la
    // petición no cuelgue el test).
    let attachAttempted = false;
    await page.route(
      (url) =>
        isBackend(url) &&
        url.pathname ===
          `/api/athletes/${ATHLETE_ID}/monthly-newsletters/attach-insights`,
      (route: Route) => {
        attachAttempted = true;
        return route.fulfill({ status: 422, json: { detail: "fallback" } });
      },
    );

    await gotoAiTab(page);

    // Panorama (subtab por defecto): el Hero muestra el estado fallback
    // pero SIN el botón "Agregar al boletín" (Wave 1, segunda ruta).
    const hero = page.getByTestId("hero-last-insight-card");
    await expect(hero).toBeVisible();
    await expect(hero.getByTestId("hero-insight-fallback-badge")).toBeVisible();
    await expect(hero.getByText(FALLBACK_SUMMARY_TEXT)).toBeVisible();
    await expect(page.getByTestId("hero-btn-add-newsletter")).toHaveCount(0);

    // Histórico: la misma fila tampoco tiene checkbox.
    await page.getByTestId("ai-subtab-history").click();
    await expect(
      page.getByTestId(`insight-checkbox-${FALLBACK_ONLY.id}`),
    ).toHaveCount(0);

    // Sin selección posible, la barra sticky nunca puede aparecer.
    await expect(page.getByTestId("newsletter-action-bar")).toHaveCount(0);

    // Verificación final: ninguna de las dos rutas disparó la petición.
    expect(attachAttempted).toBe(false);
  });
});
