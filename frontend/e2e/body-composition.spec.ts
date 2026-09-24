// E2E: Composición corporal por pliegues cutáneos (feature 046).
//
// Requiere el stack e2e AISLADO de la feature 040 (frontend/scripts/e2e-stack.sh),
// no el compose de desarrollo diario ("me"): backend propio en :8001 con datos
// sintéticos. Ver docs/21-body-composition/qa.md §2 (T072) para el estado de
// ejecución de este archivo.
//
// Cubre (quickstart.md §5): captura con un sitio omitido y una tercera lectura,
// restauración del borrador tras recargar, la tarjeta del coach con Σ4 y
// "estimado", la tarjeta de la familia con solo banda + frase (sin cifras) y
// el aviso de intervalo mínimo antes de 90 días.
//
// Privacidad: usa el atleta 1 del seed (Santiago Lopez, vinculado a
// padre@trochayruta.com); nunca se imprime su nombre en aserciones ni logs.

import { expect, test, type Page } from "@playwright/test";

const COACH_EMAIL = "entrenador@trochyruta.com";
const COACH_PASSWORD = "Coach2026!";
const PARENT_EMAIL = "padre@trochayruta.com";
const PARENT_PASSWORD = "Parent2026!";

// Atleta 1 del seed: nacido 2014-03-15, con parte vinculado — mayor de 9 años
// en cualquier fecha de esta suite, así que la salida de pliegues siempre
// está disponible.
const ATHLETE_ID = 1;

async function login(page: Page, email: string, password: string) {
  await page.goto("/login");
  await page.getByRole("textbox", { name: /correo/i }).fill(email);
  await page.getByRole("textbox", { name: /contraseña/i }).fill(password);
  await page.getByRole("button", { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

/** Llena el formulario de peso/talla y dispara "Guardar y agregar pliegues". */
async function createAnthropometryRecordAndOpenSkinfolds(page: Page) {
  await page.goto(`/athletes/${ATHLETE_ID}?tab=anthropometry`);
  await page.getByRole("button", { name: /\+ nueva medición/i }).click();
  await page.getByLabel(/fecha de evaluación/i).fill(todayIso());
  await page.getByLabel(/peso \(kg\)/i).fill("46.0");
  await page.getByLabel(/talla de pie/i).fill("156.0");
  await page.getByLabel(/talla sentado/i).fill("74.0");

  const skinfoldsButton = page.getByRole("button", { name: /guardar y agregar pliegues/i });
  await expect(skinfoldsButton).toBeVisible({ timeout: 15_000 });
  await skinfoldsButton.click();

  await expect(page).toHaveURL(/\/athletes\/\d+\/anthropometry\/\d+\/skinfolds/, {
    timeout: 15_000,
  });
  await expect(page.getByTestId("skinfold-wizard")).toBeVisible();
}

async function fillSiteReadings(page: Page, reading1: string, reading2: string) {
  await page.getByLabel(/primera lectura \(mm\)/i).fill(reading1);
  await page.getByLabel(/segunda lectura \(mm\)/i).fill(reading2);
}

test.describe("Composición corporal por pliegues cutáneos", () => {
  // Serial a propósito: el segundo caso depende del set de pliegues creado
  // por el primero (intervalo mínimo entre tomas) y el tercero (vista de la
  // familia) depende de que ya exista al menos una toma para el atleta.
  test.describe.configure({ mode: "serial" });

  test("coach captura pliegues (con omisión y tercera lectura), restaura un borrador y ve Σ4 estimado", async ({
    page,
  }) => {
    await login(page, COACH_EMAIL, COACH_PASSWORD);
    await createAnthropometryRecordAndOpenSkinfolds(page);

    // Paso 1 — Preparación (recordatorios no bloqueantes).
    await expect(page.getByRole("heading", { name: /antes de empezar/i })).toBeVisible();
    await page.getByRole("button", { name: /^siguiente$/i }).click();

    // Sitio 1 — Tríceps: lecturas normales, sin tercera lectura.
    await expect(page.getByRole("heading", { name: /^tríceps$/i })).toBeVisible();
    await fillSiteReadings(page, "8.5", "9.0");
    await page.getByRole("button", { name: /^siguiente$/i }).click();

    // Sitio 2 — Bíceps: lecturas normales.
    await expect(page.getByRole("heading", { name: /^bíceps$/i })).toBeVisible();
    await fillSiteReadings(page, "6.0", "6.5");
    await page.getByRole("button", { name: /^siguiente$/i }).click();

    // Sitio 3 — Subescapular: diferencia > tolerancia → exige tercera lectura.
    await expect(page.getByRole("heading", { name: /^subescapular$/i })).toBeVisible();
    await fillSiteReadings(page, "7.0", "8.5");
    // `getByText(/tercera lectura/i)` sin acotar matchea DOS elementos (el
    // aviso `role="status"` y el `<label>` del campo) — Playwright strict
    // mode lo rechaza. El `<p role="status">` no tiene `aria-label`, así
    // que su nombre accesible queda vacío (`status` sólo admite "name from
    // author", no "from content") — `getByRole(..., {name})` no lo
    // encuentra. Se filtra por contenido de texto en vez del nombre
    // accesible. El campo en sí ya lo verifica la línea siguiente al
    // rellenarlo.
    await expect(
      page.getByRole("status").filter({ hasText: /tercera lectura/i }),
    ).toBeVisible();
    await page.getByLabel(/tercera lectura \(mm\)/i).fill("8.0");

    // Recarga a mitad de captura: el borrador debe sobrevivir en localStorage
    // y ofrecer restaurar en vez de perder las lecturas ya tomadas.
    await page.reload();
    const draftBanner = page.getByTestId("skinfold-draft-banner");
    await expect(draftBanner).toBeVisible({ timeout: 15_000 });
    await draftBanner.getByRole("button", { name: /restaurar/i }).click();
    await expect(page.getByRole("heading", { name: /^subescapular$/i })).toBeVisible();
    await expect(page.getByLabel(/primera lectura \(mm\)/i)).toHaveValue("7");
    await expect(page.getByLabel(/tercera lectura \(mm\)/i)).toHaveValue("8");
    await page.getByRole("button", { name: /^siguiente$/i }).click();

    // Sitio 4 — Pantorrilla medial: lecturas normales.
    await expect(page.getByRole("heading", { name: /^pantorrilla medial$/i })).toBeVisible();
    await fillSiteReadings(page, "10.0", "10.5");
    await page.getByRole("button", { name: /^siguiente$/i }).click();

    // Sitio 5 — Cresta ilíaca: se omite (no forma parte de Σ4, así que la
    // suma sigue completa para la tarjeta del coach).
    await expect(page.getByRole("heading", { name: /^cresta ilíaca$/i })).toBeVisible();
    await page.getByRole("button", { name: /omitir este sitio/i }).click();

    // Sitio 6 — Supraespinal: lecturas normales.
    await expect(page.getByRole("heading", { name: /^supraespinal$/i })).toBeVisible();
    await fillSiteReadings(page, "9.0", "9.5");
    await page.getByRole("button", { name: /^siguiente$/i }).click();

    // Revisión: Σ4 debe verse completo (tríceps/bíceps/subescapular/pantorrilla,
    // ninguno omitido) — Σ6 sí queda incompleto porque se omitió la cresta
    // ilíaca, así que la aserción se limita a la fila de Σ4.
    await expect(page.getByRole("heading", { name: /revisar medición/i })).toBeVisible();
    const sum4Label = page.getByText(/^Σ4 \(tríceps/);
    const sum4Value = sum4Label.locator("xpath=following-sibling::span[1]");
    await expect(sum4Value).not.toHaveText(/suma incompleta/i);
    await page.getByRole("button", { name: /guardar medición/i }).click();

    // Vuelve al perfil, pestaña Crecimiento, con la tarjeta ya alimentada.
    await expect(page).toHaveURL(/\/athletes\/\d+\?tab=growth/, { timeout: 15_000 });
    const card = page.getByTestId("body-composition-card");
    await expect(card).toBeVisible({ timeout: 15_000 });
    await expect(card).toContainText(/Σ4/);
    await expect(card).toContainText(/\d+\.\d mm/); // Σ4 con un valor numérico real, no "—"
    await expect(card).toContainText(/estimado/i);
  });

  test("una segunda evaluación dentro de 90 días muestra el aviso de intervalo mínimo", async ({
    page,
  }) => {
    await login(page, COACH_EMAIL, COACH_PASSWORD);
    await page.goto(`/athletes/${ATHLETE_ID}?tab=anthropometry`);
    await page.getByRole("button", { name: /\+ nueva medición/i }).click();
    await page.getByLabel(/fecha de evaluación/i).fill(todayIso());
    await page.getByLabel(/peso \(kg\)/i).fill("46.2");
    await page.getByLabel(/talla de pie/i).fill("156.2");
    await page.getByLabel(/talla sentado/i).fill("74.2");

    const intervalNote = page.getByTestId("skinfolds-interval-note");
    await expect(intervalNote).toBeVisible({ timeout: 15_000 });
    await expect(intervalNote).toContainText(/próxima toma puede hacerse desde el/i);
    await expect(
      page.getByRole("button", { name: /guardar y agregar pliegues/i }),
    ).toHaveCount(0);
  });

  test("la familia ve solo banda y frase, nunca cifras", async ({ page }) => {
    await login(page, PARENT_EMAIL, PARENT_PASSWORD);
    await page.goto(`/my-athletes/${ATHLETE_ID}?tab=growth`);

    const card = page.getByTestId("family-body-composition-card");
    await expect(card).toBeVisible({ timeout: 15_000 });

    const cardText = (await card.innerText()).trim();
    // Sin porcentajes, milímetros ni ninguna cifra numérica: solo banda + frase.
    expect(cardText).not.toMatch(/%/);
    expect(cardText).not.toMatch(/\bmm\b/i);
    expect(cardText).not.toMatch(/\d/);

    // No debe existir en esta vista ninguna de las cifras/controles del coach.
    await expect(page.getByTestId("body-composition-card")).toHaveCount(0);
  });
});
