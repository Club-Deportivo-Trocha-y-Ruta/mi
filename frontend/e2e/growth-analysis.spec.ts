// E2E — feature 042 (Traceable AI growth analysis), Wave 3, T077.
//
// Coach journey: generate -> render -> reopen from cache, on the "Crecimiento"
// tab's measurement dialog.
//
// Requiere STACK REAL (NO mocks — a diferencia de cold-start.spec.ts /
// ai-insights-coach.spec.ts):
//   - docker compose up (backend real en http://localhost:8000 + MySQL).
//   - AI_ENABLED=true en el backend, con un proveedor real configurado
//     (AI_PROVIDER=... / AI_USE_LANGCHAIN en cualquiera de sus dos valores —
//     ambos deben producir el mismo resultado observable, SC-006). El
//     proveedor `fake` NO sirve para este spec: no ejerce la espera real de
//     20-40 s que este archivo asume ni produce un `schema_version="v2"`
//     estructurado con el pipeline de cinco pasos.
//   - Seed con el atleta demo (el de menor id con mediciones antropométricas,
//     resuelto por API vía `resolveDemoAthleteId`) vinculado a un padre con
//     consentimiento de IA activo (`third_party_sharing=True`) — mismo
//     requisito que `anthropometry-record-explanation.spec.ts`. Sin ese
//     consentimiento la generación responde 451 y el coach ve
//     "record-explanation-error" en vez de "record-explanation-pending".
//
// Por qué NO se mockea nada: el objetivo del test es precisamente la espera
// real (el backend del coach tarda 20-40 s en generar, y Render en
// producción tiene un cold start de ~50 s adicionales) — un mock de
// `page.route()` respondería instantáneo y no ejercería en absoluto la copy
// escalonada de `frontend/src/lib/ai/pendingMessage.ts` que este spec verifica
// (FR-032 en espíritu: "nunca un spinner desnudo").
//
// Cobertura (tasks.md T077):
//   1. Abrir el tab Crecimiento del atleta demo y el diálogo de detalle de su
//      medición más reciente (el modal migrado a la primitiva compartida,
//      T075 — foco trapado, control de cierre >=48 px).
//   2. Lanzar (o relanzar) el análisis IA de esa medición y verificar que la
//      espera muestra copy real y escalonada, nunca un spinner desnudo:
//      "Analizando esta medición..." -> "Consultando modelo de IA..." a
//      partir de los 20 s (`SLOW_THRESHOLD_MS`), potencialmente
//      "El servidor está despertando..." si además hay cold start.
//   3. El resultado renderiza el análisis estructurado (`StructuredInsight`)
//      COLAPSADO por defecto (FR-026): resumen visible, detalle
//      ("Qué significa" / "Próximas 2-4 semanas") detrás de un expansor con
//      `aria-expanded`/`aria-controls`. Se expande y se verifica el detalle.
//   4. Cerrar el diálogo y volver a abrirlo: el contenido se sirve de la
//      caché de React Query (`staleTime: Infinity` en
//      `useMeasurementExplanationCached`) — se verifica contando peticiones
//      POST de red que NO se dispara una segunda generación.
//   5. Volver a montar el tab Crecimiento (cambiando a "Antropometría" y de
//      vuelta) para forzar el refetch de `useGrowthSummary` — la mutation de
//      generación no invalida esa query mientras el tab permanece montado
//      (no hay una segunda petición de por medio, per SC-008) — y verificar
//      que la línea de resumen (`LatestAnalysisLine`, T073/T074) ahora
//      muestra la misma línea de resumen que el diálogo, en estado
//      "current" (no "none").
//
// Privacidad (Ley 1581): ningún nombre real, fecha de nacimiento ni medida
// concreta de un menor se hardcodea aquí — todos los asserts son
// estructurales (data-testid, roles, presencia/ausencia de contenido).
import { expect, test, type Page } from "@playwright/test";

import { gotoDemoAthlete, loginAsCoach } from "./helpers/demo-athlete";

// El análisis real del coach tarda 20-40 s (docstring de
// `pendingMessage.ts`); sumado a un eventual cold start de Render (~50 s,
// no aplica al stack local de docker compose pero se deja margen igual que
// `cup-vs-championship.spec.ts`/`race-analysis-championship.spec.ts`) y a
// las dos navegaciones del recorrido, el test completo puede tardar varios
// minutos.
const TEST_TIMEOUT_MS = 240_000;
// Ventana en la que debe aparecer el mensaje de "consultando modelo" — el
// umbral en código es 20 s (`SLOW_THRESHOLD_MS`); se da margen amplio antes
// de fallar por si la generación real corre más lenta de lo típico.
const ESCALATION_TIMEOUT_MS = 60_000;
// Ventana total para que la generación termine — cubre el rango 20-40 s
// típico más un eventual cold start.
const GENERATION_TIMEOUT_MS = 150_000;

const POST_EXPLANATION_PATH = /\/api\/ai\/athletes\/\d+\/measurements\/\d+\/explanation$/;

async function openGrowthTab(page: Page): Promise<void> {
  const growthTabButton = page.getByRole("button", { name: /^Crecimiento$/i });
  await expect(growthTabButton).toBeVisible({ timeout: 15_000 });
  await growthTabButton.click();
  await expect(page).toHaveURL(/\/athletes\/\d+\?tab=growth/);
  await expect(page.getByTestId("growth-tab")).toBeVisible();
}

/** Abre el diálogo de detalle de la medición más reciente (primera fila de
 *  la tabla desktop) DENTRO del historial embebido del tab Crecimiento
 *  (T075: primitiva `Dialog` compartida, no el modal legado). */
async function openLatestMeasurementDialog(page: Page): Promise<void> {
  const desktopTable = page.getByTestId("anthropometry-history-desktop");
  await expect(desktopTable).toBeVisible({ timeout: 15_000 });
  await desktopTable.getByRole("row").nth(1).click();
  await expect(
    page.getByTestId("anthropometry-record-explanation-section"),
  ).toBeVisible();
}

async function closeMeasurementDialog(page: Page): Promise<void> {
  await page.getByRole("button", { name: /^Cerrar$/i }).click();
  await expect(
    page.getByTestId("anthropometry-record-explanation-section"),
  ).toBeHidden();
}

test.describe("Análisis de crecimiento con IA — recorrido del coach", () => {
  test("E2E-042-077: generar, ver colapsado/expandido, reabrir desde caché y reflejarse en el resumen del tab", async ({
    page,
  }) => {
    test.setTimeout(TEST_TIMEOUT_MS);

    // Cuenta las peticiones POST de generación para poder afirmar más abajo
    // que reabrir el diálogo NO dispara una segunda generación (la lectura
    // en caché es un GET, nunca un POST).
    const generationRequests: string[] = [];
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        POST_EXPLANATION_PATH.test(new URL(request.url()).pathname)
      ) {
        generationRequests.push(request.url());
      }
    });

    await loginAsCoach(page);
    await gotoDemoAthlete(page, "growth");
    await openGrowthTab(page);
    await openLatestMeasurementDialog(page);

    // ------------------------------------------------------------------
    // 1) Lanzar (o relanzar) el análisis — idle vs. ya cacheado de una
    //    corrida previa de este mismo spec, igual criterio que
    //    `anthropometry-record-explanation.spec.ts`. En cualquiera de los
    //    dos casos el botón dispara la MISMA mutation de generación, así
    //    que el resto del recorrido (espera escalonada, colapso, caché) se
    //    ejerce igual.
    // ------------------------------------------------------------------
    const idle = page.getByTestId("record-explanation-idle");
    const cachedSuccess = page.getByTestId("record-explanation-success");
    await expect(idle.or(cachedSuccess).first()).toBeVisible({ timeout: 15_000 });

    if (await idle.isVisible().catch(() => false)) {
      await page
        .getByRole("button", { name: /Analizar esta medición/i })
        .click();
    } else {
      await page.getByRole("button", { name: /Regenerar análisis/i }).click();
    }

    // ------------------------------------------------------------------
    // 2) La espera real: nunca un spinner desnudo. La sección "pending"
    //    aparece con la frase inicial de inmediato, y — si la generación
    //    corre en el rango real de 20-40 s que este flujo asume — escala a
    //    la frase de "consultando modelo" pasados los 20 s
    //    (`SLOW_THRESHOLD_MS` en `pendingMessage.ts`). Si la generación
    //    terminara sospechosamente rápido (<20 s) esta aserción fallaría:
    //    es la señal correcta de que el timing real cambió, no algo a
    //    debilitar.
    // ------------------------------------------------------------------
    const pending = page.getByTestId("record-explanation-pending");
    await expect(pending).toBeVisible({ timeout: 5_000 });
    await expect(pending).toContainText(/analizando esta medición/i);

    await expect(pending).toContainText(/consultando modelo de ia/i, {
      timeout: ESCALATION_TIMEOUT_MS,
    });

    // ------------------------------------------------------------------
    // 3) Resultado: el análisis estructurado se renderiza COLAPSADO.
    // ------------------------------------------------------------------
    const success = page.getByTestId("record-explanation-success");
    await expect(success).toBeVisible({ timeout: GENERATION_TIMEOUT_MS });
    expect(
      generationRequests.length,
      "una sola petición POST de generación tras el primer lanzamiento",
    ).toBe(1);

    const structuredInsight = page.getByTestId("structured-insight");
    await expect(structuredInsight).toBeVisible();
    await expect(page.getByTestId("structured-insight-details")).toHaveCount(0);
    const toggle = page.getByTestId("structured-insight-toggle");
    await expect(toggle).toHaveAttribute("aria-expanded", "false");

    const summaryLine = await page
      .getByTestId("structured-insight-summary")
      .innerText();
    expect(summaryLine.trim().length).toBeGreaterThan(0);

    // Expandir: "qué significa" y "próximas 2-4 semanas" aparecen.
    await toggle.click();
    await expect(toggle).toHaveAttribute("aria-expanded", "true");
    const details = page.getByTestId("structured-insight-details");
    await expect(details).toBeVisible();
    await expect(page.getByTestId("structured-insight-meaning")).toBeVisible();
    await expect(page.getByTestId("structured-insight-next-weeks")).toBeVisible();

    // ------------------------------------------------------------------
    // 4) Cerrar y reabrir: debe venir de caché, sin una segunda generación.
    // ------------------------------------------------------------------
    await closeMeasurementDialog(page);
    await openLatestMeasurementDialog(page);

    // Servido desde la caché de React Query (`staleTime: Infinity`) — debe
    // asentarse en éxito rápido, sin pasar por "pending" de nuevo.
    await expect(page.getByTestId("record-explanation-success")).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByTestId("structured-insight-summary")).toHaveText(
      summaryLine,
    );

    // Margen corto para confirmar la AUSENCIA de una segunda petición POST
    // (no hay forma de "esperar a que algo no pase" salvo una ventana fija).
    await page.waitForTimeout(2_000);
    expect(
      generationRequests.length,
      "reabrir el diálogo no debe disparar una segunda generación",
    ).toBe(1);

    await closeMeasurementDialog(page);

    // ------------------------------------------------------------------
    // 5) El resumen del tab Crecimiento (`LatestAnalysisLine`) refleja el
    //    análisis recién generado. La mutation de generación no invalida
    //    `["growth-summary", athleteId]` (esa query sigue montada mientras
    //    el tab Crecimiento no se desmonta), así que se fuerza un remount
    //    real navegando a otro tab y de vuelta — la misma acción que haría
    //    un coach en la app, sin recargar la página.
    // ------------------------------------------------------------------
    await page.getByRole("button", { name: /^Antropometr[ií]a$/i }).click();
    await expect(page).toHaveURL(/\/athletes\/\d+\?tab=anthropometry/);

    const growthSummaryResponse = page.waitForResponse(
      (r) => /\/growth-summary(?:\?|$)/.test(r.url()) && r.status() === 200,
      { timeout: 20_000 },
    );
    await openGrowthTab(page);
    await growthSummaryResponse;

    const latestAnalysisLine = page.getByTestId("latest-analysis-line");
    await expect(latestAnalysisLine).toBeVisible({ timeout: 15_000 });
    await expect(latestAnalysisLine).toHaveAttribute("data-state", "current");
    await expect(latestAnalysisLine).toContainText(summaryLine);
    await expect(
      latestAnalysisLine.getByTestId("latest-analysis-line-link"),
    ).toHaveText(/Ver análisis completo/i);
  });
});
