import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { Sparkline } from "@/components/athletes/growth/Sparkline";

describe("Sparkline", () => {
  it("no renderiza nada con un arreglo vacío de valores", () => {
    const { container } = render(<Sparkline values={[]} ariaLabel="Sin datos" />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renderiza un único punto (círculo) sin polyline cuando hay un solo valor", () => {
    const { container } = render(<Sparkline values={[150]} ariaLabel="Una medición" />);
    expect(container.querySelector("polyline")).not.toBeInTheDocument();
    expect(container.querySelector("circle")).toBeInTheDocument();
  });

  it("renderiza una polyline con un punto por cada valor cuando hay 2 o más", () => {
    const values = [140, 142.5, 145, 148];
    const { container } = render(<Sparkline values={values} ariaLabel="Cuatro mediciones" />);
    const polyline = container.querySelector("polyline");
    expect(polyline).toBeInTheDocument();
    const points = polyline?.getAttribute("points")?.trim().split(/\s+/) ?? [];
    expect(points).toHaveLength(values.length);
  });

  it("acentúa el último punto (círculo aparte, en el color de acento)", () => {
    const { container } = render(<Sparkline values={[140, 145, 150]} ariaLabel="Tendencia" />);
    const circle = container.querySelector("circle");
    expect(circle).toHaveAttribute("fill", "var(--color-primary)");
  });

  it("no revienta con valores planos (mismo valor repetido)", () => {
    const { container } = render(<Sparkline values={[150, 150, 150]} ariaLabel="Sin cambio" />);
    expect(container.querySelector("polyline")).toBeInTheDocument();
    // Ningún NaN filtrado a los atributos del SVG.
    expect(container.innerHTML).not.toMatch(/NaN/);
  });

  it("expone role=img y el aria-label recibido (nunca sólo el trazo)", () => {
    render(<Sparkline values={[140, 145, 150]} ariaLabel="Evolución de talla, últimas 3 mediciones" />);
    expect(
      screen.getByRole("img", { name: "Evolución de talla, últimas 3 mediciones" }),
    ).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad (axe)", async () => {
    const { container } = render(<Sparkline values={[140, 145, 150]} ariaLabel="Tendencia de talla" />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
