import { StrictMode } from "react";
import { describe, expect, it, vi } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import {
  capturingPlausibilityHandler,
  plausibilityNetworkErrorHandler,
} from "@/test/msw/anthropometryHandlers";
import { makeBodyCompositionOut } from "@/test/msw/bodyCompositionHandlers";
import { PLAUSIBILITY_COPY } from "@/lib/anthropometry/plausibilityCopy";
import { phvPlainLabel } from "@/lib/anthropometry/phvPlain";
import { calculatePHV } from "@/lib/phv";
import { computeAgeDecimal } from "@/lib/category";
import type { AnthropometryCaptureValues } from "@/schemas/anthropometryCapture.schema";
import type { PlausibilityCheckRequest } from "@/types/anthropometry.types";
import { Sex } from "@/types/enums";

import { CaptureReviewStep, type CaptureReviewStepProps } from "../CaptureReviewStep";

// Fixtures ficticias: sin nombres ni datos reales de menores.
const ATHLETE_ID = 17;
const BIRTH_12Y = "2014-03-01";
const BIRTH_8Y = "2018-01-01";

const VALUES: AnthropometryCaptureValues = {
  evaluation_date: "2026-09-20",
  weight_kg: 45.5,
  standing_height_cm: 150,
  sitting_height_cm: 112, // lectura bruta sobre el banco
  bench_height_cm: 40,
  arm_span_cm: null,
  notes: null,
};

function bodyCompositionNextDue(nextDue: string | null) {
  return http.get("*/api/athletes/:athleteId/body-composition", () =>
    HttpResponse.json(makeBodyCompositionOut({ athlete_id: ATHLETE_ID, next_due_date: nextDue })),
  );
}

function renderReview(overrides: Partial<CaptureReviewStepProps> = {}) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const props: CaptureReviewStepProps = {
    mode: "create",
    athleteId: ATHLETE_ID,
    athleteSex: Sex.M,
    athleteBirthDate: BIRTH_12Y,
    values: VALUES,
    onRemeasure: vi.fn(),
    onSave: vi.fn(),
    ...overrides,
  };
  const utils = render(
    <QueryClientProvider client={client}>
      <CaptureReviewStep {...props} />
    </QueryClientProvider>,
  );
  return { ...utils, props };
}

describe("CaptureReviewStep", () => {
  it("muestra la talla neta, avisos con copia exacta y el resumen PHV llano", async () => {
    const sink: PlausibilityCheckRequest[] = [];
    mswServer.use(
      capturingPlausibilityHandler(sink, [
        { code: "sitting_ratio_atypical", measure: "sitting_height" },
        { code: "weight_change_large", measure: "weight" },
      ]),
      bodyCompositionNextDue(null),
    );
    const user = userEvent.setup();
    const { container, props } = renderReview();

    // Valores: talla sentado neta 112 − 40 = 72,0 cm.
    const list = screen.getByTestId("capture-review-values-list");
    expect(within(list).getByText("72,0 cm")).toBeInTheDocument();
    expect(within(list).getByText("Lectura 112,0 cm − banco 40,0 cm")).toBeInTheDocument();
    expect(within(list).getByText("No registrada")).toBeInTheDocument();
    expect(within(screen.getByTestId("capture-review-values-table")).getByText("72,0 cm")).toBeInTheDocument();

    // Avisos con la copia exacta de contracts/ui.md.
    expect(await screen.findByText(PLAUSIBILITY_COPY.sitting_ratio_atypical)).toBeInTheDocument();
    expect(screen.getByText(PLAUSIBILITY_COPY.weight_change_large)).toBeInTheDocument();

    // El dry-run envía la talla NETA y, al crear, sin record_id.
    expect(sink).toHaveLength(1);
    expect(sink[0]).toMatchObject({
      evaluation_date: "2026-09-20",
      weight_kg: 45.5,
      standing_height_cm: 150,
      sitting_height_cm: 72,
      arm_span_cm: null,
    });
    expect(sink[0]).not.toHaveProperty("record_id");
    expect(JSON.stringify(sink[0])).not.toContain("bench");

    // PHV en lenguaje llano.
    const expected = calculatePHV({
      sex: Sex.M,
      ageDecimal: computeAgeDecimal(new Date(`${BIRTH_12Y}T00:00:00`), new Date("2026-09-20T00:00:00")),
      weightKg: 45.5,
      standingHeightCm: 150,
      sittingHeightCm: 72,
    });
    expect(expected).not.toBeNull();
    expect(
      within(screen.getByTestId("phv-plain-summary")).getByText(phvPlainLabel(expected!.maturationStatus)),
    ).toBeInTheDocument();

    // «Volver a medir» avisa al orquestador con la medida.
    const alerts = screen.getAllByRole("note");
    const sittingAlert = alerts.find((a) =>
      a.textContent?.includes(PLAUSIBILITY_COPY.sitting_ratio_atypical),
    )!;
    await user.click(within(sittingAlert).getByRole("button", { name: "Volver a medir" }));
    expect(props.onRemeasure).toHaveBeenCalledWith("sitting_height");

    // «Está bien así» oculta el aviso sin bloquear el guardado.
    await user.click(within(sittingAlert).getByRole("button", { name: "Está bien así" }));
    expect(screen.queryByText(PLAUSIBILITY_COPY.sitting_ratio_atypical)).not.toBeInTheDocument();

    expect(await axe(container)).toHaveNoViolations();
  });

  it("ofrece «Guardar y agregar pliegues» con ≥ 9 años e intervalo abierto", async () => {
    const sink: PlausibilityCheckRequest[] = [];
    mswServer.use(capturingPlausibilityHandler(sink), bodyCompositionNextDue(null));
    const user = userEvent.setup();
    const { props } = renderReview();

    const skinfolds = await screen.findByRole("button", { name: "Guardar y agregar pliegues" });
    await user.click(skinfolds);
    expect(props.onSave).toHaveBeenCalledWith("skinfolds");

    await user.click(screen.getByRole("button", { name: "Guardar y terminar" }));
    expect(props.onSave).toHaveBeenLastCalledWith("finish");
    expect(screen.queryByTestId("skinfolds-interval-note")).not.toBeInTheDocument();
  });

  it("oculta la salida de pliegues con menos de 9 años", async () => {
    mswServer.use(capturingPlausibilityHandler([]), bodyCompositionNextDue(null));
    renderReview({ athleteBirthDate: BIRTH_8Y });

    expect(await screen.findByRole("button", { name: "Guardar y terminar" })).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
    expect(screen.queryByRole("button", { name: "Guardar y agregar pliegues" })).not.toBeInTheDocument();
    expect(screen.queryByTestId("skinfolds-interval-note")).not.toBeInTheDocument();
  });

  it("con el intervalo cerrado oculta la salida y muestra la nota del 046", async () => {
    mswServer.use(capturingPlausibilityHandler([]), bodyCompositionNextDue("2026-12-19"));
    renderReview();

    const note = await screen.findByTestId("skinfolds-interval-note");
    expect(note).toHaveTextContent("Pliegues cutáneos: la próxima toma puede hacerse desde el");
    expect(screen.queryByRole("button", { name: "Guardar y agregar pliegues" })).not.toBeInTheDocument();
  });

  it("en edición envía record_id y ofrece una sola salida «Guardar cambios»", async () => {
    const sink: PlausibilityCheckRequest[] = [];
    mswServer.use(capturingPlausibilityHandler(sink), bodyCompositionNextDue(null));
    const user = userEvent.setup();
    const { container, props } = renderReview({
      mode: "edit",
      recordId: 812,
      values: { ...VALUES, sitting_height_cm: 72, bench_height_cm: 0 },
    });

    await waitFor(() => expect(sink).toHaveLength(1));
    expect(sink[0]).toMatchObject({ record_id: 812, sitting_height_cm: 72 });

    const buttons = screen.getAllByRole("button").filter((b) => b.textContent?.startsWith("Guardar"));
    expect(buttons.map((b) => b.textContent)).toEqual(["Guardar cambios"]);
    await user.click(buttons[0]);
    expect(props.onSave).toHaveBeenCalledWith("finish");
    // Sin banco no se muestra el desglose bruto/banco.
    expect(screen.queryByText(/− banco/)).not.toBeInTheDocument();

    expect(await axe(container)).toHaveNoViolations();
  });

  it("guardando: botón «Guardando…» deshabilitado; error con «Reintentar»", async () => {
    mswServer.use(capturingPlausibilityHandler([]), bodyCompositionNextDue(null));
    const user = userEvent.setup();
    const onRetry = vi.fn();
    const { rerender, props } = renderReview({ isSaving: true, pendingIntent: "finish" });

    const saving = screen.getByRole("button", { name: "Guardando…" });
    expect(saving).toBeDisabled();

    const client = new QueryClient();
    rerender(
      <QueryClientProvider client={client}>
        <CaptureReviewStep
          {...props}
          isSaving={false}
          pendingIntent={null}
          saveError="Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar."
          onRetry={onRetry}
        />
      </QueryClientProvider>,
    );
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Sin conexión — no se guardó. Revisa tu conexión y vuelve a intentar.",
    );
    await user.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    // Los valores siguen en pantalla.
    expect(within(screen.getByTestId("capture-review-values-list")).getByText("72,0 cm")).toBeInTheDocument();
  });

  it("si el dry-run falla, no bloquea el guardado", async () => {
    mswServer.use(plausibilityNetworkErrorHandler, bodyCompositionNextDue(null));
    renderReview();
    expect(await screen.findByTestId("plausibility-check-error")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Guardar y terminar" })).toBeEnabled();
  });
  it("en StrictMode (dev) el dry-run termina: no queda en «Revisando las medidas…»", async () => {
    // Regresión hallada en e2e (T056): con la guarda sin limpiar, el
    // desmontaje simulado de StrictMode desuscribía el observador de la
    // mutación y el panel quedaba en «Revisando las medidas…» para siempre.
    const sink: PlausibilityCheckRequest[] = [];
    mswServer.use(
      capturingPlausibilityHandler(sink, [{ code: "weight_change_large", measure: "weight" }]),
      bodyCompositionNextDue(null),
    );
    const client = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    render(
      <StrictMode>
        <QueryClientProvider client={client}>
          <CaptureReviewStep
            mode="create"
            athleteId={ATHLETE_ID}
            athleteSex={Sex.M}
            athleteBirthDate={BIRTH_12Y}
            values={VALUES}
            onRemeasure={vi.fn()}
            onSave={vi.fn()}
          />
        </QueryClientProvider>
      </StrictMode>,
    );

    expect(await screen.findByText(PLAUSIBILITY_COPY.weight_change_large)).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.queryByText("Revisando las medidas…")).not.toBeInTheDocument(),
    );
  });
});
