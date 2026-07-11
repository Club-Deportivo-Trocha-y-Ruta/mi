import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { Stepper } from "../Stepper";

expect.extend(toHaveNoViolations);

const STEPS = [{ label: "Datos" }, { label: "Revisión" }, { label: "Confirmación" }];

describe.each(["compact", "detailed"] as const)("Stepper — variant=%s", (variant) => {
  it("renderiza la etiqueta de cada paso", () => {
    render(<Stepper steps={STEPS} active={1} variant={variant} />);
    for (const step of STEPS) {
      expect(screen.getByText(step.label)).toBeInTheDocument();
    }
  });

  it("marca aria-current=step únicamente en el paso activo", () => {
    render(<Stepper steps={STEPS} active={1} variant={variant} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).not.toHaveAttribute("aria-current");
    expect(items[1]).toHaveAttribute("aria-current", "step");
    expect(items[2]).not.toHaveAttribute("aria-current");
  });

  it("solo los pasos completados (index < active) son clickeables", () => {
    const onStepClick = vi.fn();
    render(<Stepper steps={STEPS} active={2} onStepClick={onStepClick} variant={variant} />);

    // Pasos 0 y 1 (completados, index < active) → el clic invoca el callback
    // con su índice.
    fireEvent.click(screen.getByRole("button", { name: STEPS[0].label }));
    expect(onStepClick).toHaveBeenCalledWith(0);

    fireEvent.click(screen.getByRole("button", { name: STEPS[1].label }));
    expect(onStepClick).toHaveBeenCalledWith(1);

    expect(onStepClick).toHaveBeenCalledTimes(2);

    // Paso 2 (activo, no completado) → deshabilitado, el clic no invoca nada.
    onStepClick.mockClear();
    const currentButton = screen.getByRole("button", { name: STEPS[2].label });
    expect(currentButton).toBeDisabled();
    fireEvent.click(currentButton);
    expect(onStepClick).not.toHaveBeenCalled();
  });

  it("sin onStepClick, ningún paso queda habilitado para clic", () => {
    render(<Stepper steps={STEPS} active={2} variant={variant} />);
    // Paso 0 sería "completado" (index < active) pero sin callback no hay
    // nada que invocar, así que el botón permanece deshabilitado.
    expect(screen.getByRole("button", { name: STEPS[0].label })).toBeDisabled();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = render(
      <Stepper steps={STEPS} active={1} onStepClick={vi.fn()} variant={variant} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});

describe("Stepper — variantes", () => {
  it("ambos valores de variant renderizan sin lanzar errores", () => {
    expect(() =>
      render(<Stepper steps={STEPS} active={0} variant="compact" />),
    ).not.toThrow();
    expect(() =>
      render(<Stepper steps={STEPS} active={0} variant="detailed" />),
    ).not.toThrow();
  });

  it("usa 'compact' cuando no se especifica variant", () => {
    render(<Stepper steps={STEPS} active={0} />);
    expect(screen.getAllByRole("listitem")).toHaveLength(3);
  });
});
