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
const PARENT_EMAIL = "padre@trochayruta.com";
const PARENT_PASSWORD = "Parent2026!";

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByRole('textbox', { name: /correo/i }).fill(email);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(password);
  await page.getByRole("button", { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function openFirstAthleteAnthropometryTab(page: Page) {
  // Sidebar coach: "Atletas". Las filas de la tabla no navegan; el link "Ver" sí.
  await page.getByRole("link", { name: /^atletas$/i }).click();
  await expect(page).toHaveURL(/\/athletes/);
  const anthroResponse = page.waitForResponse(
    (r) => /\/anthropometry/.test(r.url()) && r.status() === 200,
    { timeout: 30_000 },
  );
  await page.getByRole("link", { name: /^Ver$/ }).first().click();
  await expect(page).toHaveURL(/\/athletes\/\d+/);
  await anthroResponse;
  // El botón del tab lleva acento: "Antropometría".
  await page.getByRole("button", { name: /antropometr[ií]a/i }).click();
  // Esperar a que el historial (desktop) termine de montar para que el caller
  // pueda asumir estado estable (evita la carrera del check historyExists).
  await page
    .getByTestId("anthropometry-history-desktop")
    .waitFor({ state: "visible", timeout: 15_000 })
    .catch(() => {
      /* El atleta podría no tener mediciones; el caller lo maneja. */
    });
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
      await page.getByRole("button", { name: /nueva medici[óo]n/i }).click();
      await page.getByLabel(/peso \(kg\)/i).fill("45.5");
      await page.getByLabel(/talla de pie/i).fill("155.0");
      await page.getByLabel(/talla sentado/i).fill("73.0");
      await page.getByLabel(/fecha de evaluaci[óo]n/i).fill("2026-04-14");
      await page.getByRole("button", { name: /guardar medici[óo]n/i }).click();
    }

    await openFirstMeasurementDetail(page);

    const idle = page.getByTestId("record-explanation-idle");
    const success = page.getByTestId("record-explanation-success");

    // El estado del modal puede tardar (fetch de la caché). Esperamos a que
    // se asiente en idle (sin caché) o success (caché previa) antes de decidir.
    await expect(idle.or(success).first()).toBeVisible({ timeout: 15_000 });

    if (await idle.isVisible().catch(() => false)) {
      // Sin caché → generar.
      await page
        .getByRole("button", { name: /Analizar esta medición/i })
        .click();
    } else {
      // Hay caché → regenerar para forzar una nueva generación.
      await page.getByRole("button", { name: /Regenerar/i }).click();
    }

    // En ambos caminos, al final debe verse el contenido generado.
    await expect(success).toBeVisible({ timeout: 30_000 });
    await expect(page.getByTestId("ai-generated-content")).toBeVisible();
  });

  test("padre lee la explicación cacheada con disclaimer obligatorio", async ({
    browser,
  }) => {
    // El padre del seed (padre@trochayruta.com) está vinculado al atleta 1
    // (Santiago Lopez), que tiene mediciones. El coach debe sembrar la caché
    // del análisis SOBRE ESE MISMO atleta (no su primer atleta de la lista),
    // para que el padre lea la explicación ya generada de su hijo.
    const PARENT_CHILD_ATHLETE_ID = 1;

    // ── Coach genera la explicación de una medición del atleta 1 ──
    const coachContext = await browser.newContext();
    const coachPage = await coachContext.newPage();
    await login(coachPage, COACH_EMAIL, COACH_PASSWORD);
    // Deep-link directo al tab Antropometría del hijo del padre.
    await coachPage.goto(`/athletes/${PARENT_CHILD_ATHLETE_ID}?tab=anthropometry`);
    await expect(
      coachPage.getByTestId("anthropometry-history-desktop"),
    ).toBeVisible({ timeout: 15_000 });
    await openFirstMeasurementDetail(coachPage);
    const idle = coachPage.getByTestId("record-explanation-idle");
    const coachSuccess = coachPage.getByTestId("record-explanation-success");
    if (await idle.isVisible().catch(() => false)) {
      await coachPage
        .getByRole("button", { name: /Analizar esta medición/i })
        .click();
    }
    // Tras generar (o si ya había caché) debe verse el contenido exitoso.
    await expect(coachSuccess).toBeVisible({ timeout: 30_000 });
    await coachContext.close();

    // ── Padre lee la explicación cacheada de su hijo ──
    const parentContext = await browser.newContext();
    const parentPage = await parentContext.newPage();
    await login(parentPage, PARENT_EMAIL, PARENT_PASSWORD);

    // El padre navega al detalle de su hijo desde "Mis Atletas".
    await expect(parentPage).toHaveURL(/\/my-athletes/);
    await parentPage
      .getByRole("link", { name: /ver detalle de santiago/i })
      .first()
      .click();
    await expect(parentPage).toHaveURL(/\/my-athletes\/\d+/);

    // En el portal del padre, el historial vive bajo el tab "Crecimiento"
    // (no hay tab "Antropometría"); ahí la tabla de mediciones es clickeable.
    await parentPage.getByRole("button", { name: /crecimiento/i }).click();
    const desktopTable = parentPage.getByTestId("anthropometry-history-desktop");
    await expect(desktopTable).toBeVisible({ timeout: 15_000 });
    await desktopTable.getByRole("row").nth(1).click();
    await expect(
      parentPage.getByTestId("anthropometry-record-explanation-section"),
    ).toBeVisible();

    // El padre ve el modo readOnly con disclaimer
    await expect(
      parentPage.getByTestId("record-explanation-readonly"),
    ).toBeVisible({ timeout: 30_000 });
    await expect(
      parentPage.getByTestId("record-explanation-disclaimer"),
    ).toContainText(/IA.*entrenador.*médico/i);
    // El padre NO ve botones de generación/regeneración (solo lectura)
    await expect(
      parentPage.getByRole("button", { name: /Analizar esta medición/i }),
    ).toHaveCount(0);
    await expect(
      parentPage.getByRole("button", { name: /Regenerar/i }),
    ).toHaveCount(0);

    await parentContext.close();
  });
});
