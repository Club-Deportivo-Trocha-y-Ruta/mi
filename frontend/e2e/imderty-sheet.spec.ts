/**
 * E2E — planilla mensual de asistencia IMDERTY (feature 047, T052).
 *
 * Cubre `quickstart.md` §3–5 con la pila e2e AISLADA (feature 040,
 * `frontend/scripts/e2e-stack.sh` — backend propio en :8001, MySQL propio):
 * el coach abre la página de la planilla, ve un hueco de disponibilidad del
 * atleta demo, lo resuelve desde el "Perfil IMDERTY" de la ficha, confirma
 * que el hueco desaparece del panel y descarga el workbook de un mes
 * (evento `download` + nombre de archivo `FO-GDD-057_asistencia_*.xlsx`).
 *
 * Sigue el patrón de `frontend/e2e/helpers/demo-athlete.ts` (mismo atleta
 * demo que `anthropometry.spec.ts` / `body-composition.spec.ts`) y de
 * `growth.spec.ts` para el `download` event. No hay mocks de `page.route()`
 * — corre contra un backend FastAPI real (ver nota VERBATIM sobre
 * `VITE_API_BASE_URL` en `playwright.config.ts`).
 *
 * Serial a propósito: el segundo bloque (mobile) reutiliza el estado
 * "documento vacío" que deja el primer bloque en el atleta demo si se
 * interrumpe a medio camino — cada test dentro del primer `describe` deja
 * al atleta en un estado conocido antes de continuar, así que no importa
 * el orden de ejecución entre archivos, pero sí dentro de este.
 *
 * Privacidad (Ley 1581): el atleta demo es sintético (seed de
 * `docker-compose.e2e.yml`); nunca se imprime su nombre, solo su id
 * numérico, igual que el resto de specs de esta suite.
 */
import { expect, test, type Page } from '@playwright/test';

import { COACH_EMAIL, COACH_PASSWORD, loginAsCoach, resolveDemoAthleteId } from './helpers/demo-athlete';

const READINESS_RE = /\/imderty-sheet\/readiness/;
const PROFILE_PUT_RE = /\/imderty-profile$/;

/**
 * Fila (desktop, `<tr>`) del panel de disponibilidad para un atleta.
 *
 * `ReadinessPanel` pinta la tabla desktop y la lista mobile a la vez (una se
 * oculta con `hidden md:block` / `md:hidden`, no se desmonta) — cada una
 * trae su propio enlace "Ver atleta" con el mismo `href`. `getByRole('row')`
 * solo matchea `<tr>` (la tabla), así que no hay ambigüedad con la `<li>`
 * de la vista mobile aunque ambas existan en el DOM.
 */
function desktopReadinessRow(page: Page, athleteId: number) {
  const link = page.locator(`a[href="/athletes/${athleteId}?tab=imderty#imderty-profile"]`);
  return page.getByRole('row').filter({ has: link });
}

/** Card (mobile, `<li>`) del panel de disponibilidad para un atleta — ver nota arriba. */
function mobileReadinessCard(page: Page, athleteId: number) {
  const link = page.locator(`a[href="/athletes/${athleteId}?tab=imderty#imderty-profile"]`);
  return page.getByRole('listitem').filter({ has: link });
}

/** Espera a que el panel de disponibilidad termine de cargar (sale el skeleton). */
async function waitForReadinessLoaded(page: Page) {
  await page.waitForResponse((r) => READINESS_RE.test(r.url()) && r.status() === 200);
  await expect(page.getByRole('status', { name: /cargando disponibilidad/i })).toHaveCount(0);
}

/** Deja el documento del atleta demo vacío (garantiza el hueco `missing_document`). */
async function clearAthleteDocument(page: Page, athleteId: number) {
  // Forma legada (sin `?tab`): la ficha la normaliza a la pestaña «Perfil
  // IMDERTY» conservando el ancla — se ejercita acá a propósito.
  await page.goto(`/athletes/${athleteId}#imderty-profile`);
  await expect(page).toHaveURL(new RegExp(`/athletes/${athleteId}\\?tab=imderty#imderty-profile`));
  await expect(page.getByRole('heading', { name: /perfil imderty/i })).toBeVisible({
    timeout: 15_000,
  });

  const typeCombobox = page.getByRole('combobox', { name: /tipo de documento/i });
  await typeCombobox.click();
  await page.getByRole('option', { name: /sin especificar/i }).click();

  const numberInput = page.getByLabel(/número de documento/i);
  await numberInput.fill('');

  const putResponse = page.waitForResponse(
    (r) => PROFILE_PUT_RE.test(r.url()) && r.request().method() === 'PUT' && r.status() === 200,
  );
  await page.getByRole('button', { name: /guardar perfil/i }).click();
  await putResponse;
  await expect(page.getByText(/perfil imderty actualizado/i)).toBeVisible();
}

test.describe('Planilla IMDERTY (feature 047)', () => {
  test.describe.configure({ mode: 'serial' });

  test('el coach ve un hueco de disponibilidad, lo resuelve desde el perfil del atleta y descarga la planilla del mes', async ({
    page,
  }) => {
    await loginAsCoach(page);
    const athleteId = await resolveDemoAthleteId(page.request);

    // Paso 0 — deja el documento vacío para que el hueco `missing_document`
    // exista sin depender de corridas anteriores de esta misma suite.
    await clearAthleteDocument(page, athleteId);

    // Paso 1 — la página de la planilla muestra el hueco "Falta documento"
    // para el atleta demo.
    await page.goto('/imderty/planilla');
    await expect(page).toHaveURL(/\/imderty\/planilla/);
    await waitForReadinessLoaded(page);

    const rowBefore = desktopReadinessRow(page, athleteId);
    await expect(rowBefore).toBeVisible({ timeout: 15_000 });
    await expect(rowBefore.getByText('Falta documento', { exact: true })).toBeVisible();

    // Paso 2 — el coach corrige el perfil IMDERTY desde el enlace "Ver atleta".
    await rowBefore.getByRole('link', { name: /ver atleta/i }).click();
    await expect(page).toHaveURL(new RegExp(`/athletes/${athleteId}\\?tab=imderty#imderty-profile`));
    await expect(page.getByRole('heading', { name: /perfil imderty/i })).toBeVisible({
      timeout: 15_000,
    });

    await page.getByRole('combobox', { name: /tipo de documento/i }).click();
    await page.getByRole('option', { name: 'T.I' }).click();
    await page.getByLabel(/número de documento/i).fill('1029384756');

    const putResponse = page.waitForResponse(
      (r) => PROFILE_PUT_RE.test(r.url()) && r.request().method() === 'PUT' && r.status() === 200,
    );
    await page.getByRole('button', { name: /guardar perfil/i }).click();
    await putResponse;
    await expect(page.getByText(/perfil imderty actualizado/i)).toBeVisible();

    // Paso 3 — de vuelta en la planilla, el hueco "Falta documento" ya no
    // aparece para este atleta (puede seguir teniendo otros huecos, p. ej.
    // apellidos sin confirmar — eso no es parte de este flujo).
    await page.goto('/imderty/planilla');
    await waitForReadinessLoaded(page);

    const rowAfter = desktopReadinessRow(page, athleteId);
    if (await rowAfter.count()) {
      await expect(rowAfter.getByText('Falta documento', { exact: true })).toHaveCount(0);
    }
    // Si `rowAfter` ya no existe, el atleta no tiene ningún hueco pendiente
    // — también es una resolución válida del hueco que se aseguró arriba.

    // Paso 4 — descarga la planilla del mes seleccionado por defecto
    // (mes anterior al actual, precargado por `ImdertySheetPage`).
    const downloadPromise = page.waitForEvent('download');
    await page.getByRole('button', { name: /descargar planilla/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/^FO-GDD-057_asistencia_.*\.xlsx$/);
  });

  test('mobile — el panel de disponibilidad muestra el hueco del atleta demo como card', async ({
    page,
  }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/login');
    await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
    await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
    await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
    await expect(page).not.toHaveURL(/\/login/);

    const athleteId = await resolveDemoAthleteId(page.request);

    // El primer test de este archivo ya dejó el documento del atleta demo
    // resuelto (o el atleta sin huecos); vuelve a vaciarlo para que la
    // vista mobile también tenga un hueco real que mostrar, sin volver a
    // aserciones de escritorio.
    await clearAthleteDocument(page, athleteId);

    await page.goto('/imderty/planilla');
    await waitForReadinessLoaded(page);

    // A este ancho, la tabla desktop está oculta (`hidden md:block`) y la
    // lista mobile (`ul role="list" md:hidden`) es la que se ve.
    await expect(page.getByRole('table')).toBeHidden();
    const mobileList = page.getByRole('list');
    await expect(mobileList).toBeVisible({ timeout: 15_000 });

    const row = mobileReadinessCard(page, athleteId);
    await expect(row).toBeVisible();
    await expect(row.getByText('Falta documento', { exact: true })).toBeVisible();
    await expect(row.getByRole('link', { name: /ver atleta/i })).toBeVisible();
  });
});
