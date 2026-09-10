/**
 * E2E — Conflicto de edición concurrente en el estudio del boletín
 * (feature 041 — gobernanza multi-coach, US5). Contrato:
 * specs/041-multi-coach-governance/contracts/concurrency-and-approvals.md
 *
 * Dos entrenadores (coach y coach2), cada uno en su propio
 * `BrowserContext`, abren el mismo boletín. Ambos cargan `edit_version: 1`.
 * coach2 guarda primero (PATCH exitoso, sube a `edit_version: 2`); cuando
 * coach guarda con su `expected_version` desactualizado (1), el backend
 * simulado responde `409 { current_version: 2 }` y la UI debe abrir el
 * diálogo de conflicto bloqueante + banner pinneado, según
 * `AthleteNewsletterStudioPage` (testids `newsletter-conflict-dialog`,
 * `newsletter-conflict-banner`, `newsletter-conflict-reload`).
 *
 * Backend mockeado vía `page.route` en cada contexto — mismo patrón de
 * `newsletters-coach.spec.ts` — con un estado de versión COMPARTIDO entre
 * ambos contextos (misma corrida de Node) para simular la base de datos
 * real que ambos entrenadores comparten.
 */
import { test, expect, type Browser, type Page, type Route } from "@playwright/test";
import { realTokens } from "./helpers/session";

const ATHLETE_ID = 201;
const NEWSLETTER_ID = 501;

const COACH_A_USER = {
  id: 10,
  first_name: "Ana",
  last_name: "Coach",
  email: "entrenador@trochyruta.com",
  phone: null,
  role: "coach",
  is_active: true,
  can_login: true,
  club_ids: [1],
  created_at: "2026-01-01T00:00:00Z",
};

const COACH_B_USER = {
  ...COACH_A_USER,
  id: 11,
  first_name: "Bruno",
  last_name: "Coach",
  email: "entrenador2@trochyruta.com",
};

const ATHLETE_FIXTURE = {
  id: ATHLETE_ID,
  user_id: 9001,
  first_name: "Valentina",
  last_name: "Garcia",
  birth_date: "2013-04-12",
  sex: "F",
  club_join_date: "2024-02-01",
  years_in_club: 2,
  age_decimal: 13.1,
  category: "Pre-Infantil",
  club_id: 1,
  created_at: "2024-02-01T00:00:00Z",
  latest_anthropometry: null,
};

/** Estado "de base de datos" compartido por ambos contextos de este test. */
interface SharedNewsletterState {
  editVersion: number;
  coachNote: string | null;
}

function makeNewsletter(state: SharedNewsletterState) {
  return {
    id: NEWSLETTER_ID,
    athlete_id: ATHLETE_ID,
    year: 2026,
    month: 5,
    status: "draft",
    edit_version: state.editVersion,
    email_blocks: {},
    ai_narrative: null,
    coach_narrative_overrides: null,
    coach_note: state.coachNote,
    stage_overrides: {},
    hidden_blocks: [],
    selected_race_insight_ids: [],
    badges_earned: [],
    has_pdf: false,
    pdf_generated_at: null,
    pdf_sha256: null,
    generated_by_user_id: COACH_A_USER.id,
    approved_by_user_id: null,
    approved_at: null,
    sent_at: null,
    error_message: null,
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  };
}

async function mockBackend(
  page: Page,
  user: typeof COACH_A_USER,
  state: SharedNewsletterState,
) {
  await page.route("**/api/auth/me", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(user) }),
  );

  await page.route(`**/api/athletes/${ATHLETE_ID}`, (route: Route) => {
    if (route.request().method() !== "GET") return route.continue();
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(ATHLETE_FIXTURE),
    });
  });

  await page.route(
    `**/api/athletes/${ATHLETE_ID}/monthly-newsletters/${NEWSLETTER_ID}`,
    async (route: Route) => {
      const method = route.request().method();

      if (method === "GET") {
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(makeNewsletter(state)),
        });
      }

      if (method === "PATCH") {
        const body = route.request().postDataJSON() as {
          expected_version: number;
          coach_note?: string;
        };
        if (body.expected_version !== state.editVersion) {
          // 041 §2.5 — conflicto de versión: el único 409 con current_version.
          return route.fulfill({
            status: 409,
            contentType: "application/json",
            body: JSON.stringify({
              detail: "El boletín fue editado por otra persona. Recarga para ver la versión más reciente.",
              current_version: state.editVersion,
            }),
          });
        }
        state.editVersion += 1;
        if (typeof body.coach_note === "string") state.coachNote = body.coach_note;
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(makeNewsletter(state)),
        });
      }

      return route.continue();
    },
  );

  await page.route("**/api/parent-athletes/my-athletes", (route: Route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );
}

async function setupAuth(page: Page, role: "coach" | "coach2", user: typeof COACH_A_USER) {
  const tokens = await realTokens(page.request, role);
  await page.addInitScript(
    ({ accessToken, refreshToken, sessionUser }) => {
      sessionStorage.setItem(
        "auth-session",
        JSON.stringify({
          state: {
            accessToken,
            refreshToken,
            user: sessionUser,
            isAuthenticated: true,
            isLoading: false,
          },
          version: 0,
        }),
      );
    },
    { accessToken: tokens.access_token, refreshToken: tokens.refresh_token, sessionUser: user },
  );
}

async function openStudio(page: Page) {
  await page.goto(`/training/athlete-newsletters/${ATHLETE_ID}/${NEWSLETTER_ID}`);
  await expect(page.getByTestId("newsletter-studio-page")).toBeVisible({ timeout: 15_000 });
}

test.describe("Newsletter concurrent-edit conflict E2E", () => {
  test("E2E-NLC-001: la segunda coach en guardar recibe 409 y ve el diálogo de conflicto bloqueante", async ({
    browser,
  }: {
    browser: Browser;
  }) => {
    const shared: SharedNewsletterState = { editVersion: 1, coachNote: null };

    const contextA = await browser.newContext();
    const contextB = await browser.newContext();
    const pageA = await contextA.newPage();
    const pageB = await contextB.newPage();

    await mockBackend(pageA, COACH_A_USER, shared);
    await mockBackend(pageB, COACH_B_USER, shared);
    await setupAuth(pageA, "coach", COACH_A_USER);
    await setupAuth(pageB, "coach2", COACH_B_USER);

    // Ambos entrenadores abren el mismo boletín; ambos cargan edit_version=1.
    await openStudio(pageA);
    await openStudio(pageB);

    // coach2 (Bruno) guarda primero — su PATCH usa expected_version=1,
    // coincide, éxito, edit_version pasa a 2.
    const noteFieldB = pageB.getByTestId("coach-note");
    await noteFieldB.fill("Nota de Bruno: excelente sesión técnica esta semana.");
    await noteFieldB.blur();
    await expect(pageB.getByTestId("newsletter-conflict-dialog")).toHaveCount(0);

    // coach (Ana) sigue viendo edit_version=1 en su formulario local y
    // guarda ahora — su PATCH manda expected_version=1, pero el estado
    // "compartido" ya está en 2 → 409 con current_version=2.
    const noteFieldA = pageA.getByTestId("coach-note");
    await noteFieldA.fill("Nota de Ana: trabajar cadencia en subidas.");
    await noteFieldA.blur();

    // El diálogo bloqueante de conflicto aparece.
    await expect(pageA.getByTestId("newsletter-conflict-dialog")).toBeVisible({
      timeout: 5_000,
    });
    // El banner pinneado también queda visible detrás del diálogo.
    await expect(pageA.getByTestId("newsletter-conflict-banner")).toBeVisible();

    // "Seguir editando" cierra el diálogo pero el banner se mantiene (el
    // draft no se descarta solo).
    await pageA.getByTestId("newsletter-conflict-keep-editing").click();
    await expect(pageA.getByTestId("newsletter-conflict-dialog")).toBeHidden();
    await expect(pageA.getByTestId("newsletter-conflict-banner")).toBeVisible();

    // "Recargar" es la única salida: limpia el conflicto y refleja la
    // versión más reciente (la nota de Bruno).
    await pageA.getByTestId("newsletter-conflict-banner").getByRole("button").click();
    await expect(pageA.getByTestId("newsletter-conflict-banner")).toHaveCount(0, {
      timeout: 5_000,
    });

    await contextA.close();
    await contextB.close();
  });
});
