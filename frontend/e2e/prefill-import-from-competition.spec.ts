/**
 * E2E spec 015 — Prefill results import from an existing competition
 *
 * Cubre los acceptance criteria de spec 015: al lanzar la importación desde
 * una competencia, el wizard abre precargado y bloqueado; el campeonato oculta
 * "Válida #"; el flujo standalone queda intacto; el camino bloqueado ofrece
 * "Editar metadata"; y no aparece PII de menores antes del dry-run.
 *
 * Stack real (no mocks):
 *   - Backend FastAPI en http://localhost:8000 (seed dev/Docker aplicado).
 *   - Frontend Vite en http://localhost:5173 (reuseExistingServer).
 *
 * Los ids de competencia se DESCUBREN vía el backend (no se hardcodean) para
 * resistir cambios de seed. Privacidad: NUNCA se hardcodean nombres ni DOB de
 * menores; los asserts son estructurales (data-testid, roles, headings).
 */
import { test, expect, type Page } from "@playwright/test";

const COACH = { email: "entrenador@trochyruta.com", password: "Coach2026!" };
const BACKEND = "http://localhost:8000";

const COLD_START_TIMEOUT = 90_000;
const NAV_TIMEOUT = 30_000;

// ---------------------------------------------------------------------------
// Login — mismo patrón que cup-vs-championship.spec.ts
// ---------------------------------------------------------------------------

async function login(
  page: Page,
  creds: { email: string; password: string },
): Promise<void> {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(creds.email);
  await page.getByRole("textbox", { name: /contraseña/i }).fill(creds.password);
  await page.getByRole("button", { name: /ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/, { timeout: COLD_START_TIMEOUT });
  await expect
    .poll(
      async () =>
        page.evaluate(() => {
          const raw = sessionStorage.getItem("auth-session");
          if (!raw) return false;
          try {
            return JSON.parse(raw)?.state?.isAuthenticated === true;
          } catch {
            return false;
          }
        }),
      { timeout: 10_000 },
    )
    .toBe(true);
}

async function getToken(page: Page): Promise<string> {
  return page.evaluate(() => {
    const raw = sessionStorage.getItem("auth-session");
    if (!raw) return "";
    try {
      return JSON.parse(raw)?.state?.accessToken ?? "";
    } catch {
      return "";
    }
  });
}

interface RaceEventListItem {
  id: number;
  is_championship: boolean;
  status: string;
  has_results: boolean;
}

/** Descubre ids de una válida (copa) y un campeonato desde el backend. */
async function discoverEventIds(
  page: Page,
  token: string,
): Promise<{ cupId: number | null; championshipId: number | null }> {
  const data = await page.evaluate(
    async ({ backend, t }) => {
      const res = await fetch(`${backend}/api/race-analysis/race-events/`, {
        headers: { Authorization: `Bearer ${t}` },
      });
      return res.ok ? await res.json() : { items: [] };
    },
    { backend: BACKEND, t: token },
  );
  const items: RaceEventListItem[] = data.items ?? [];
  const cup = items.find((e) => !e.is_championship && e.status === "completed");
  const championship = items.find((e) => e.is_championship);
  return {
    cupId: cup?.id ?? null,
    championshipId: championship?.id ?? null,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

test.describe("Spec 015 — prefill import from competition", () => {
  test.beforeEach(async ({ page }) => {
    await login(page, COACH);
  });

  test("copa: prefill bloqueado, válida visible, llega al upload sin re-tecleo", async ({
    page,
  }) => {
    const token = await getToken(page);
    const { cupId } = await discoverEventIds(page, token);
    test.skip(cupId == null, "Seed sin válida copa completada");

    await page.goto(`/competitions/${cupId}/import`);
    const summary = page.getByTestId("prefill-locked-summary");
    await expect(summary).toBeVisible({ timeout: NAV_TIMEOUT });

    // Identidad bloqueada (no inputs editables de tipo/serie/evento).
    await expect(page.getByTestId("wizard-series-kind")).toHaveCount(0);
    await expect(page.getByTestId("wizard-series-name")).toHaveCount(0);
    await expect(summary).toContainText("Copa");
    await expect(summary).toContainText(/Válida #/i);

    // Escape hatch presente y el botón Continuar (upload) disponible.
    await expect(page.getByTestId("prefill-edit-metadata")).toBeVisible();
    await expect(page.getByTestId("wizard-step1-submit")).toBeVisible();
  });

  test("campeonato: oculta 'Válida #' y muestra tipo Campeonato", async ({
    page,
  }) => {
    const token = await getToken(page);
    const { championshipId } = await discoverEventIds(page, token);
    test.skip(championshipId == null, "Seed sin campeonato");

    await page.goto(`/competitions/${championshipId}/import`);
    const summary = page.getByTestId("prefill-locked-summary");
    await expect(summary).toBeVisible({ timeout: NAV_TIMEOUT });
    await expect(summary).toContainText("Campeonato");
    await expect(summary).not.toContainText(/Válida #/i);
  });

  test("standalone: /competitions/import sigue editable y sin locking", async ({
    page,
  }) => {
    await page.goto("/competitions/import");
    // El selector de tipo editable existe; no hay resumen prefill.
    await expect(page.getByTestId("wizard-series-kind")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    await expect(page.getByTestId("prefill-locked-summary")).toHaveCount(0);
    await expect(page.getByTestId("prefill-blocked")).toHaveCount(0);
  });

  test("privacidad: no aparece nombre de atleta antes del dry-run", async ({
    page,
  }) => {
    const token = await getToken(page);
    const { cupId } = await discoverEventIds(page, token);
    test.skip(cupId == null, "Seed sin válida copa completada");

    await page.goto(`/competitions/${cupId}/import`);
    await expect(page.getByTestId("prefill-locked-summary")).toBeVisible({
      timeout: NAV_TIMEOUT,
    });
    // El paso 2 (matches con nombres) no debe existir todavía.
    await expect(page.getByTestId("import-wizard-step2")).toHaveCount(0);
  });
});
