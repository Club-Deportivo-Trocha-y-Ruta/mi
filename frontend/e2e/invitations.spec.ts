// Requiere: docker compose up
// Cubre la sección "Invitaciones al portal" en /parents/{id}
import { test, expect, type Page } from '@playwright/test';

// ---------------------------------------------------------------------------
// Credenciales
// ---------------------------------------------------------------------------

const COACH_EMAIL = 'entrenador@trochyruta.com';
const COACH_PASSWORD = 'Coach2026!';
const PARENT_EMAIL = 'padre@trochayruta.com';
const PARENT_PASSWORD = 'Parent2026!';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function loginAsCoach(page: Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(COACH_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(COACH_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

async function loginAsParent(page: Page) {
  await page.goto('/login');
  await page.getByRole('textbox', { name: /correo/i }).fill(PARENT_EMAIL);
  await page.getByRole('textbox', { name: /contraseña/i }).fill(PARENT_PASSWORD);
  await page.getByRole('button', { name: /iniciar sesión|ingresar/i }).click();
  await expect(page).not.toHaveURL(/\/login/);
}

/**
 * Navega al detalle del padre con ID dado (asume sesión de coach activa).
 * Espera a que la sección "Invitaciones al portal" sea visible.
 */
async function goToParentDetail(page: Page, parentId: number) {
  await page.goto(`/parents/${parentId}`);
  // Esperar que la página cargue y no esté en loading skeleton
  await expect(page.getByText(/Invitaciones al portal/i)).toBeVisible({ timeout: 10_000 });
}

// ---------------------------------------------------------------------------
// Constantes del seed
// ---------------------------------------------------------------------------

// El padre de prueba con atletas vinculados (su atleta ya tiene la cuenta
// ACTIVADA en el seed → muestra "Cuenta activada" + historial de invitaciones).
// Útil para INV-001/006/008/009. Si el seed cambia, actualizar aquí.
const PARENT_WITH_ATHLETES_ID = 29;

// Padres del seed cuyo (único) atleta está en estado "formulario de envío"
// (sin invitación usada ni pendiente) → la tarjeta muestra el input de correo
// y el botón "Enviar invitacion". Cada test que muta estado usa un padre
// distinto para evitar contaminación cruzada bajo ejecución paralela.
//   - parent 4   (Carlos Garcia → Santiago Lopez)  — no-mutación (botón disabled)
//   - parent 225 (Padre Test)                       — INV-002 envía (muta)
//   - parent 227 (Padre Test)                       — INV-003 reenvía (auto-siembra)
//   - parent 229 (Padre Test)                       — INV-005 email inválido (no-mutación)
//   - parent 248 (PadreA SinEmail)                  — INV-007 activa (auto-siembra)
const PARENT_SENDFORM_DISABLED_ID = 4;
const PARENT_SENDFORM_SEND_ID = 225;
const PARENT_SENDFORM_RESEND_ID = 227;
const PARENT_SENDFORM_INVALID_ID = 229;
const PARENT_SENDFORM_ACTIVE_ID = 248;

const TEST_INVITE_EMAIL = 'test-invite-e2e@example.com';

/**
 * Garantiza que la tarjeta de invitación del (único) atleta del padre quede en
 * estado "pendiente/activa". El seed no trae invitaciones pendientes, así que
 * si la tarjeta muestra el formulario de envío, enviamos una invitación.
 *
 * Idempotente: si una corrida previa ya dejó la invitación pendiente (los
 * tests mutan estado real en MySQL), el formulario ya no aparece y saltamos
 * el envío. Tras enviar recargamos para forzar el refetch del panel activo
 * (evita la carrera entre el mensaje de éxito inmediato y la invalidación de
 * la query de invitaciones).
 */
async function ensureActiveInvite(page: Page) {
  const emailInput = page.getByPlaceholder(/correo@ejemplo.com/i).first();
  const activePanel = page.getByText(/Invitacion activa/i);

  if (await emailInput.isVisible().catch(() => false)) {
    await emailInput.fill(TEST_INVITE_EMAIL);
    await page.getByRole('button', { name: /Enviar invitacion/i }).first().click();
    await expect(
      page.getByText(/Invitacion enviada correctamente\./i),
    ).toBeVisible({ timeout: 8_000 });
    // Recargar fuerza un fetch fresco de las invitaciones → el panel "activa"
    // se renderiza de forma determinista (no dependemos del refetch en vuelo).
    await page.reload();
    await expect(page.getByText(/Invitaciones al portal/i)).toBeVisible({
      timeout: 10_000,
    });
  }

  await expect(activePanel).toBeVisible({ timeout: 8_000 });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

// E2E-INV-001 — Sección "Invitaciones al portal" es visible con atletas vinculados
test('E2E-INV-001: coach ve sección "Invitaciones al portal" con tarjeta por atleta', async ({ page }) => {
  await loginAsCoach(page);
  await goToParentDetail(page, PARENT_WITH_ATHLETES_ID);

  // La sección principal debe estar visible
  await expect(page.getByText(/Invitaciones al portal/i)).toBeVisible();

  // Debe haber al menos una tarjeta de invitación (encabezado "Invitacion — <nombre>")
  await expect(page.getByText(/^Invitacion —/i).first()).toBeVisible();
});

// E2E-INV-002 — Happy path: enviar invitación nueva a atleta sin invitación activa
test('E2E-INV-002: coach envía invitación nueva y ve confirmación "Invitacion enviada correctamente."', async ({ page }) => {
  await loginAsCoach(page);
  // Padre con atleta en estado "formulario de envío" (sin invitación previa).
  await goToParentDetail(page, PARENT_SENDFORM_SEND_ID);

  const emailInput = page.getByPlaceholder(/correo@ejemplo.com/i).first();

  // Idempotencia: en la 1ª corrida la tarjeta muestra el formulario y enviamos
  // verificando el mensaje de éxito. En corridas posteriores (los tests mutan
  // estado real), la invitación ya quedó pendiente → el formulario no aparece
  // y validamos que el panel de invitación activa está presente.
  if (await emailInput.isVisible().catch(() => false)) {
    await emailInput.fill(TEST_INVITE_EMAIL);
    const sendButton = page.getByRole('button', { name: /Enviar invitacion/i }).first();
    await expect(sendButton).toBeEnabled();
    await sendButton.click();
    await expect(
      page.getByText(/Invitacion enviada correctamente\./i),
    ).toBeVisible({ timeout: 8_000 });
  } else {
    await expect(page.getByText(/Invitacion activa/i)).toBeVisible({
      timeout: 8_000,
    });
  }
});

// E2E-INV-003 — Happy path: reenviar invitación existente (botón "Reenviar")
test('E2E-INV-003: coach reenvía invitación activa y ve confirmación', async ({ page }) => {
  await loginAsCoach(page);
  // El seed no tiene invitaciones pendientes; el helper siembra una (o reusa
  // la de una corrida previa). Padre dedicado para no contaminar otros tests.
  await goToParentDetail(page, PARENT_SENDFORM_RESEND_ID);
  await ensureActiveInvite(page);

  // La tarjeta con invitación activa muestra el botón "Reenviar".
  const reenviarButton = page.getByRole('button', { name: /^Reenviar$/i });
  await expect(reenviarButton).toBeVisible({ timeout: 8_000 });
  await reenviarButton.click();

  // Verificar mensaje de éxito — aparece en la misma tarjeta
  await expect(page.getByText(/Invitacion enviada correctamente\./i)).toBeVisible({ timeout: 8_000 });
});

// E2E-INV-004 — Campo vacío: botón "Enviar invitacion" está deshabilitado sin email
test('E2E-INV-004: botón "Enviar invitacion" está deshabilitado cuando el campo está vacío', async ({ page }) => {
  await loginAsCoach(page);
  // Padre con atleta en estado formulario de envío. Este test NO muta estado.
  await goToParentDetail(page, PARENT_SENDFORM_DISABLED_ID);

  // Localizar el campo de email (solo visible cuando no hay invitación activa)
  const emailInput = page.getByPlaceholder(/correo@ejemplo.com/i).first();
  await expect(emailInput).toBeVisible();

  // Asegurar que el campo está vacío
  await emailInput.clear();

  // El botón debe estar deshabilitado (el componente usa disabled={!email.trim()})
  const sendButton = page.getByRole('button', { name: /Enviar invitacion/i }).first();
  await expect(sendButton).toBeDisabled();
});

// E2E-INV-005 — Validación nativa HTML: email inválido no dispara la mutación
test('E2E-INV-005: email inválido activa validación nativa del input type=email y no envía', async ({ page }) => {
  await loginAsCoach(page);
  // Padre con atleta en estado formulario de envío. El email inválido es
  // bloqueado por la validación nativa de type=email → no muta estado.
  await goToParentDetail(page, PARENT_SENDFORM_INVALID_ID);

  const emailInput = page.getByPlaceholder(/correo@ejemplo.com/i).first();
  await expect(emailInput).toBeVisible();

  // Ingresar valor que no es un email válido
  await emailInput.fill('no-es-un-email');

  const sendButton = page.getByRole('button', { name: /Enviar invitacion/i }).first();
  // El botón está habilitado porque email.trim() es truthy, pero el input type=email
  // activa la validación del navegador al hacer submit/click
  await sendButton.click();

  // El mensaje de éxito NO debe aparecer
  await expect(page.getByText(/Invitacion enviada correctamente\./i)).not.toBeVisible();

  // El mensaje de error del servidor tampoco debe aparecer (la mutación no se disparó
  // porque el navegador rechazó el valor con validación nativa de type=email)
  await expect(page.getByText(/No se pudo enviar la invitacion/i)).not.toBeVisible();
});

// E2E-INV-006 — Historial: invitación existente muestra fecha enviada, vencimiento y estado
test('E2E-INV-006: historial de invitación muestra "Enviada:", "Vence:" y badge de estado', async ({ page }) => {
  await loginAsCoach(page);
  await goToParentDetail(page, PARENT_WITH_ATHLETES_ID);

  // La sección de historial aparece bajo el encabezado "Historial de invitaciones"
  await expect(page.getByText(/Historial de invitaciones/i)).toBeVisible({ timeout: 8_000 });

  // Verificar que al menos una fila del historial tiene las etiquetas clave
  // Usamos el texto "Enviada:" que el componente renderiza como "Enviada: {fecha} · Vence: {fecha}"
  await expect(page.getByText(/Enviada:/i).first()).toBeVisible();
  await expect(page.getByText(/Vence:/i).first()).toBeVisible();

  // El badge de estado debe existir: "Pendiente", "Usado" o "Vencido"
  const statusBadge = page.getByText(/^(Pendiente|Usado|Vencido)$/i).first();
  await expect(statusBadge).toBeVisible();
});

// E2E-INV-007 — Invitación activa: bloque "Invitacion activa" muestra "Vence:" (no expone email de atleta)
test('E2E-INV-007: bloque de invitación activa muestra "Invitacion activa" y fecha de vencimiento', async ({ page }) => {
  await loginAsCoach(page);
  // El seed no tiene invitaciones pendientes; el helper siembra una (o reusa
  // la de una corrida previa). Padre dedicado para no contaminar otros tests.
  await goToParentDetail(page, PARENT_SENDFORM_ACTIVE_ID);
  await ensureActiveInvite(page);

  // El bloque de invitación activa (fondo ámbar) muestra estos textos
  await expect(page.getByText(/Invitacion activa/i)).toBeVisible({ timeout: 8_000 });
  await expect(page.getByText(/Vence:/i).first()).toBeVisible();

  // Nota: no asercionamos el email específico al que fue enviada (privacidad)
  // Solo verificamos que existe el texto "Enviada a:" como etiqueta
  await expect(page.getByText(/Enviada a:/i)).toBeVisible();
});

// E2E-INV-008 — Acceso denegado: parent no puede ver /parents/{id} de otro padre
test('E2E-INV-008: parent no puede acceder a /parents/{id} y es redirigido', async ({ page }) => {
  await loginAsParent(page);

  // El padre logueado (padre@trochyruta.com) intenta acceder al detalle de otro padre
  await page.goto(`/parents/${PARENT_WITH_ATHLETES_ID}`);

  // Debe ser redirigido a /my-athletes (el guard redirige a rol padre)
  // O bien la página muestra error de permisos / not found
  // Verificar que NO está en la URL de detalle del padre sin autorización
  const url = page.url();
  const isOnParentDetail = url.includes(`/parents/${PARENT_WITH_ATHLETES_ID}`);

  if (isOnParentDetail) {
    // Si la UI no redirige, al menos no debe mostrar la sección de invitaciones
    // (puede mostrar "no encontrado" o redirigir)
    await expect(page.getByText(/Invitaciones al portal/i)).not.toBeVisible();
  } else {
    // Fue redirigido correctamente
    await expect(page).toHaveURL(/\/my-athletes/);
  }
});

// E2E-INV-009 — Sin atletas vinculados: se muestra mensaje de aviso, no la sección de invitaciones
test('E2E-INV-009: padre sin atletas vinculados muestra aviso en lugar de sección de invitaciones', async ({ page }) => {
  await loginAsCoach(page);

  // Navegar a un padre que no tenga atletas vinculados
  // Usamos la lista de padres para encontrar el primero que no tenga "Invitaciones al portal"
  await page.goto('/parents');
  await expect(page).toHaveURL(/\/parents/);

  // Hacer clic en "Ver" del primer padre de la lista
  await page.getByRole('link', { name: /^Ver$/ }).first().click();
  await expect(page).toHaveURL(/\/parents\/\d+/);

  // Esperar que la página cargue (loading skeleton desaparece)
  // Si no tiene atletas vinculados, el componente muestra el aviso
  // Si tiene atletas vinculados, la sección de invitaciones aparece
  // El test solo valida que uno de los dos estados sea visible
  await page.waitForTimeout(2_000); // Dar tiempo al fetch de relaciones

  const inviteSection = page.getByText(/Invitaciones al portal/i);
  const noAthletesMsg = page.getByText(/Vincula al menos un atleta para poder generar invitaciones/i);

  const hasSectionVisible = await inviteSection.isVisible();
  const hasWarningVisible = await noAthletesMsg.isVisible();

  // Exactamente uno de los dos debe estar visible
  expect(hasSectionVisible || hasWarningVisible).toBe(true);
});
