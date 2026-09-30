import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { MEASURE_GUIDES } from "@/lib/anthropometry/measureGuides";
import { getMeasureIllustration } from "@/lib/anthropometry/measureIllustrations";

import { MeasureStep } from "../MeasureStep";

describe("MeasureStep (T040)", () => {
  it("usa teclado decimal (inputmode) y muestra Dónde/Cómo con la ilustración", async () => {
    const { container } = render(
      <MeasureStep
        measureKey="weight"
        value={undefined}
        onChange={vi.fn()}
        onNext={vi.fn()}
        illustrationSrc={getMeasureIllustration("weight")}
      />,
    );
    const input = screen.getByLabelText("Peso (kg)");
    expect(input).toHaveAttribute("inputmode", "decimal");
    expect(screen.getByRole("heading", { name: "Dónde" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cómo" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: MEASURE_GUIDES.weight.alt })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Omitir (opcional)" })).not.toBeInTheDocument();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("envergadura ofrece «Omitir (opcional)» y lo invoca", async () => {
    const onSkip = vi.fn();
    const onNext = vi.fn();
    const user = userEvent.setup();
    const { container } = render(
      <MeasureStep
        measureKey="arm_span"
        value={undefined}
        onChange={vi.fn()}
        onPrev={vi.fn()}
        onNext={onNext}
        onSkip={onSkip}
      />,
    );
    expect(screen.getByLabelText("Envergadura (cm)")).toHaveAttribute("inputmode", "decimal");
    await user.click(screen.getByRole("button", { name: "Omitir (opcional)" }));
    expect(onSkip).toHaveBeenCalledTimes(1);
    expect(onNext).not.toHaveBeenCalled();
    expect(await axe(container)).toHaveNoViolations();
  });

  it("talla sentado: lectura del tallímetro y banco con teclado decimal", () => {
    render(
      <MeasureStep
        measureKey="sitting_height"
        value={112}
        onChange={vi.fn()}
        onNext={vi.fn()}
        benchValue={40}
        onBenchChange={vi.fn()}
        persistBench={false}
      />,
    );
    expect(screen.getByLabelText("Lectura en el tallímetro (cm)")).toHaveAttribute(
      "inputmode",
      "decimal",
    );
    expect(screen.getByLabelText("Altura del banco (cm)")).toHaveAttribute("inputmode", "decimal");
    expect(screen.getByTestId("net-sitting-height")).toHaveTextContent("72,0 cm");
  });
});
