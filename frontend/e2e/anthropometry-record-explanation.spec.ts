// E2E: Análisis particular IA de mediciones antropométricas.
//
// Requiere:
//   docker compose up
//   AI_ENABLED=true AI_PROVIDER=fake en el backend
//   Seed ejecutado: padre@trochyruta.com tiene consentimiento con third_party_sharing=True
//
// El proveedor `fake` devuelve texto determinista, permitiendo asertar
// contenido renderizado en el modal.

import { expect, test, type Page } from "@playwright/test";

const COACH_EMAIL = "entrenador@trochyruta.com";
const COACH_PASSWORD = "Coach2026!";
const PARENT_EMAIL = "padre@trochyruta.com";
const PARENT_PASSWORD = "Parent2026!";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByLabel(/email/i).fill(email);
  await page.getByLabel(/contraseña|password/i).fill(password);
  await page.getByRole("button", { name: /iniciar sesión/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function openFirstAthleteAnthropometryTab(page: Page) {
  await page.getByRole("link", { name: /atletas/i }).click();
  await expect(page).toHaveURL(/\/athletes/);
  await page.getByRole("table").getByRole("row").nth(1).click();
  await expect(page).toHaveURL(/\/athletes\/\d+/);
  await page.getByRole("button", { name: /antropometria/i }).click();
}

async function openFirstMeasurementDetail(page: Page) {
  // Click en la primera fila de la tabla de histórico (desktop) o la primera card (mobile)
  const desktopTable = page.getByTestId("anthropometry-history-desktop");
  const mobileList = page.getByTestId("anthropometry-history");
  if (await desktopTable.isVisible().catch(() => false)) {
    await desktopTable.getByRole("row").nth(1).click();
  } else {
    await mobileList.locator("li").first().click();
  }
  // El modal se identifica por la sección de análisis particular
  await expect(
    page.getByTestId("anthropometry-record-explanation-section"),
  ).toBeVisible();
}

// ---------------------------------------------------------------------------
// Coach generation flow
// ---------------------------------------------------------------------------

test.describe("Análisis particular IA por medición", () => {
  test("coach genera análisis particular para una medición existente", async ({
    page,
  }) => {
    await login(page, COACH_EMAIL, COACH_PASSWORD);
    await openFirstAthleteAnthropometryTab(page);

    // Si no hay mediciones, registramos una rápida para tener algo
    const historyExists = await page
      .getByTestId("anthropometry-history-desktop")
      .or(page.getByTestId("anthropometry-history"))
      .isVisible()
      .catch(() => false);

    if (!historyExists) {
      await page.getByRole("button", { name: /nueva medicion/i }).click();
      await page.getByLabel(/peso \(kg\)/i).fill("45.5");
      await page.getByLabel(/talla de pie/i).fill("155.0");
      await page.getByLabel(/talla sentado/i).fill("73.0");
      await page.getByLabel(/fecha de evaluacion/i).fill("2026-04-14");
      await page.getByRole("button", { name: /guardar medicion/i }).click();
    }

    await openFirstMeasurementDetail(page);

    // En estado idle, ver el botón "Analizar esta medición"
    const idle = page.getByTestId("record-explanation-idle");
    const success = page.getByTestId("record-explanation-success");
    // El estado puede ser idle (sin caché) o success (caché previa de tests anteriores)
    if (await idle.isVisible().catch(() => false)) {
      await page
        .getByRole("button", { name: /Analizar esta medición/i })
        .click();
    } else {
      // Hay caché — regenera para obtener un texto fresco del provider fake
      await expect(success).toBeVisible();
      await page.getByRole("button", { name: /Regenerar/i }).click();
    }

    // Esperar a que aparezca el contenido generado
    await expect(success).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("ai-generated-content")).toBeVisible();
  });

  test("padre lee la explicación cacheada con disclaimer obligatorio", async ({
    browser,
  }) => {
    // El coach genera primero (en otra sesión) para sembrar la caché.
    const coachContext = await browser.newContext();
    const coachPage = await coachContext.newPage();
    await login(coachPage, COACH_EMAIL, COACH_PASSWORD);
    await openFirstAthleteAnthropometryTab(coachPage);
    await openFirstMeasurementDetail(coachPage);
    const idle = coachPage.getByTestId("record-explanation-idle");
    if (await idle.isVisible().catch(() => false)) {
      await coachPage
        .getByRole("button", { name: /Analizar esta medición/i })
        .click();
      await expect(
        coachPage.getByTestId("record-explanation-success"),
      ).toBeVisible({ timeout: 30_000 });
    }
    await coachContext.close();

    // Ahora abre la sesión del padre
    const parentContext = await browser.newContext();
    const parentPage = await parentContext.newPage();
    await login(parentPage, PARENT_EMAIL, PARENT_PASSWORD);

    // El padre navega a su hijo
    await parentPage.getByRole("link", { name: /atletas/i }).click();
    await parentPage.getByRole("table").getByRole("row").nth(1).click();
    await parentPage.getByRole("button", { name: /antropometria/i }).click();
    await openFirstMeasurementDetail(parentPage);

    // El padre ve el modo readOnly con disclaimer
    await expect(
      parentPage.getByTestId("record-explanation-readonly"),
    ).toBeVisible({ timeout: 30_000 });
    await expect(
      parentPage.getByTestId("record-explanation-disclaimer"),
    ).toContainText(/IA.*entrenador.*médico/i);
    // El padre NO ve botones de generación/regeneración
    await expect(
      parentPage.getByRole("button", { name: /Analizar esta medición/i }),
    ).toHaveCount(0);
    await expect(
      parentPage.getByRole("button", { name: /Regenerar/i }),
    ).toHaveCount(0);

    await parentContext.close();
  });
});
