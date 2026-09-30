import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { BENCH_HEIGHT_KEY } from "@/lib/anthropometry/devicePrefs";
import { MaturationStatus } from "@/types/enums";
import { CapturePrecheckStep } from "../CapturePrecheckStep";
import { MeasureStep } from "../MeasureStep";
import { PhvPlainSummary } from "../PhvPlainSummary";
import { PlausibilityWarnings } from "../PlausibilityWarnings";
import { QuickCaptureForm } from "../QuickCaptureForm";

function withQuery(ui: React.ReactElement) {
  const client = new QueryClient();
  return <QueryClientProvider client={client}>{ui}</QueryClientProvider>;
}

beforeEach(() => window.localStorage.clear());

describe("QuickCaptureForm", () => {
  it("valida, muestra la talla neta y entrega valores brutos", async () => {
    window.localStorage.setItem(BENCH_HEIGHT_KEY, "30");
    const onReview = vi.fn();
    const user = userEvent.setup();
    const { container } = render(<QuickCaptureForm onReview={onReview} />);

    expect(screen.getByLabelText("Altura del banco (cm)")).toHaveValue("30");
    for (const name of ["Peso (kg)", "Talla de pie (cm)", "Lectura del tallímetro, sentado (cm)"]) {
      expect(screen.getByLabelText(name)).toHaveAttribute("inputmode", "decimal");
    }

    await user.click(screen.getByRole("button", { name: "Revisar y guardar" }));
    expect((await screen.findAllByText("Obligatorio")).length).toBeGreaterThanOrEqual(3);
    expect(onReview).not.toHaveBeenCalled();

    await user.type(screen.getByLabelText("Peso (kg)"), "45,5");
    await user.type(screen.getByLabelText("Talla de pie (cm)"), "150");
    await user.type(screen.getByLabelText("Lectura del tallímetro, sentado (cm)"), "102");
    expect(screen.getByTestId("net-sitting-height")).toHaveTextContent("Talla sentado neta: 72,0 cm");

    expect(await axe(container)).toHaveNoViolations();
    await user.click(screen.getByRole("button", { name: "Revisar y guardar" }));
    await waitFor(() => expect(onReview).toHaveBeenCalledTimes(1));
    expect(onReview.mock.calls[0][0]).toMatchObject({
      weight_kg: 45.5,
      standing_height_cm: 150,
      sitting_height_cm: 102,
      bench_height_cm: 30,
      arm_span_cm: null,
    });
  });

  it("no persiste el banco cuando persistBench es false (edición)", async () => {
    const user = userEvent.setup();
    render(<QuickCaptureForm onReview={vi.fn()} persistBench={false} />);
    expect(screen.getByLabelText("Altura del banco (cm)")).toHaveValue("0");
    await user.clear(screen.getByLabelText("Altura del banco (cm)"));
    await user.type(screen.getByLabelText("Altura del banco (cm)"), "25");
    expect(window.localStorage.getItem(BENCH_HEIGHT_KEY)).toBeNull();
  });

  it("guarda el banco en el dispositivo por defecto", async () => {
    const user = userEvent.setup();
    render(<QuickCaptureForm onReview={vi.fn()} />);
    await user.type(screen.getByLabelText("Altura del banco (cm)"), "28");
    expect(window.localStorage.getItem(BENCH_HEIGHT_KEY)).toBe("28");
  });
});

describe("MeasureStep", () => {
  it("sin ilustración no renderiza <img>; con ella usa el alt de la guía", async () => {
    const { container, rerender } = render(
      <MeasureStep measureKey="weight" value={undefined} onChange={vi.fn()} onNext={vi.fn()} />,
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByText("Dónde")).toBeInTheDocument();
    expect(screen.getByText("Cómo")).toBeInTheDocument();
    expect(screen.getByLabelText("Peso (kg)")).toHaveAttribute("inputmode", "decimal");

    rerender(
      <MeasureStep
        measureKey="weight"
        value={undefined}
        onChange={vi.fn()}
        onNext={vi.fn()}
        illustrationSrc="/x.webp"
      />,
    );
    expect(screen.getByRole("img")).toHaveAttribute("src", "/x.webp");
    expect(await axe(container)).toHaveNoViolations();
  });

  it("envergadura ofrece Omitir; sentado incluye el banco y la talla neta", async () => {
    const onSkip = vi.fn();
    const user = userEvent.setup();
    const { unmount } = render(
      <MeasureStep measureKey="arm_span" value={undefined} onChange={vi.fn()} onNext={vi.fn()} onSkip={onSkip} />,
    );
    await user.click(screen.getByRole("button", { name: "Omitir (opcional)" }));
    expect(onSkip).toHaveBeenCalled();
    unmount();

    const { container } = render(
      <MeasureStep
        measureKey="sitting_height"
        value={102}
        onChange={vi.fn()}
        onNext={vi.fn()}
        benchValue={30}
        onBenchChange={vi.fn()}
      />,
    );
    expect(screen.getByLabelText("Lectura en el tallímetro (cm)")).toBeInTheDocument();
    expect(screen.getByLabelText("Altura del banco (cm)")).toBeInTheDocument();
    expect(screen.getByTestId("net-sitting-height")).toHaveTextContent("72,0 cm");
    expect(screen.queryByRole("button", { name: "Omitir (opcional)" })).toBeNull();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("Siguiente y Anterior invocan sus callbacks", async () => {
    const onNext = vi.fn();
    const onPrev = vi.fn();
    const user = userEvent.setup();
    render(
      <MeasureStep measureKey="standing_height" value={150} onChange={vi.fn()} onNext={onNext} onPrev={onPrev} />,
    );
    await user.click(screen.getByRole("button", { name: "Siguiente" }));
    await user.click(screen.getByRole("button", { name: "Anterior" }));
    expect(onNext).toHaveBeenCalled();
    expect(onPrev).toHaveBeenCalled();
  });
});

describe("CapturePrecheckStep", () => {
  it("lista no bloqueante, fecha y Empezar", async () => {
    const onStart = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      withQuery(<CapturePrecheckStep date="2026-01-10" onDateChange={vi.fn()} onStart={onStart} />),
    );
    expect(container.querySelector("img")).toBeNull();
    expect(screen.getAllByRole("checkbox")).toHaveLength(5);
    expect(screen.getByRole("button", { name: /Instructivo/i })).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
    await user.click(screen.getByRole("button", { name: "Empezar" }));
    expect(onStart).toHaveBeenCalled();
  });

  it("sin conexión deshabilita Empezar", () => {
    render(withQuery(<CapturePrecheckStep date="2026-01-10" onDateChange={vi.fn()} onStart={vi.fn()} isOffline />));
    expect(screen.getByRole("button", { name: "Empezar" })).toBeDisabled();
    expect(screen.getByText("Necesitas conexión a internet para registrar mediciones.")).toBeInTheDocument();
  });
});

describe("PlausibilityWarnings", () => {
  it("una advertencia por aviso; Volver a medir y Está bien así", async () => {
    const onRemeasure = vi.fn();
    const onAcknowledge = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <PlausibilityWarnings
        warnings={[
          { code: "height_decreased", measure: "standing_height" },
          { code: "weight_change_large", measure: "weight" },
        ]}
        onRemeasure={onRemeasure}
        onAcknowledge={onAcknowledge}
      />,
    );
    expect(screen.getAllByRole("listitem")).toHaveLength(2);
    expect(await axe(container)).toHaveNoViolations();

    await user.click(screen.getAllByRole("button", { name: "Volver a medir" })[0]);
    expect(onRemeasure).toHaveBeenCalledWith("standing_height");

    await user.click(screen.getAllByRole("button", { name: "Está bien así" })[1]);
    expect(onAcknowledge).toHaveBeenCalledWith({ code: "weight_change_large", measure: "weight" });
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
  });

  it("sin advertencias no renderiza nada", () => {
    const { container } = render(<PlausibilityWarnings warnings={[]} onRemeasure={vi.fn()} />);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("PhvPlainSummary", () => {
  const phv = {
    legLengthCm: 80,
    legSittingRatio: 1.1,
    maturityOffset: -1.2,
    ageAtPhv: 14.1,
    maturationStatus: MaturationStatus.PrePHV,
    trainingImplications: "Habilidades, juego, coordinación.",
  };

  it("muestra la etiqueta llana y pliega el detalle técnico", async () => {
    const user = userEvent.setup();
    const { container } = render(<PhvPlainSummary phv={phv} />);
    expect(screen.getByText("Aún no llega al estirón")).toBeInTheDocument();
    expect(screen.getByText(phv.trainingImplications)).toBeInTheDocument();
    expect(screen.queryByText("Maturity offset")).toBeNull();

    await user.click(screen.getByRole("button", { name: /Detalle técnico/ }));
    expect(screen.getByText("Maturity offset")).toBeInTheDocument();
    expect(screen.getByText("14.1 años")).toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });
});
