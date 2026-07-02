/**
 * Tests para ExerciseIllustration (US1 / T018, FR-006):
 *   - Renderiza la figura ASCII envuelta en role="img" con aria-label.
 *   - Fallback de alt text cuando illustration_alt está vacío.
 *   - No renderiza nada cuando no hay figura disponible.
 *   - a11y: jest-axe sin violaciones en todos los estados.
 *
 * Mirror del espíritu de `components/technique/CircuitDiagram.a11y.test.tsx`
 * (feature 018), adaptado al fallback ASCII simple (`<pre role="img">`, sin
 * SVG estructurado — ver ExerciseIllustration.tsx).
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { ExerciseIllustration } from "../ExerciseIllustration";

expect.extend(toHaveNoViolations);

const ASCII_FIGURE = "  O\n /|\\\n / \\";
const ALT_TEXT = "Figura de una persona realizando una sentadilla con peso corporal.";

describe("ExerciseIllustration", () => {
  it("renderiza la sección 'Figura' con el <pre role=\"img\">", () => {
    render(
      <ExerciseIllustration
        illustration_ascii={ASCII_FIGURE}
        illustration_alt={ALT_TEXT}
      />,
    );

    expect(
      screen.getByRole("region", { name: "Figura del ejercicio" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Figura" })).toBeInTheDocument();
    expect(screen.getByRole("img", { name: ALT_TEXT })).toBeInTheDocument();
  });

  it("el <pre> contiene el contenido ASCII literal", () => {
    const { container } = render(
      <ExerciseIllustration
        illustration_ascii={ASCII_FIGURE}
        illustration_alt={ALT_TEXT}
      />,
    );

    const pre = container.querySelector("pre");
    expect(pre).not.toBeNull();
    expect(pre!.textContent).toContain("O");
  });

  it("usa el texto de fallback cuando illustration_alt está vacío", () => {
    render(
      <ExerciseIllustration illustration_ascii={ASCII_FIGURE} illustration_alt="" />,
    );

    expect(
      screen.getByRole("img", { name: "Figura del ejercicio de fuerza" }),
    ).toBeInTheDocument();
  });

  it("usa el texto de fallback cuando illustration_alt es solo espacios", () => {
    render(
      <ExerciseIllustration illustration_ascii={ASCII_FIGURE} illustration_alt="   " />,
    );

    expect(
      screen.getByRole("img", { name: "Figura del ejercicio de fuerza" }),
    ).toBeInTheDocument();
  });

  it("no renderiza nada cuando illustration_ascii está vacío", () => {
    const { container } = render(
      <ExerciseIllustration illustration_ascii="" illustration_alt={ALT_TEXT} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("no renderiza nada cuando illustration_ascii es solo espacios", () => {
    const { container } = render(
      <ExerciseIllustration illustration_ascii="   " illustration_alt={ALT_TEXT} />,
    );

    expect(container).toBeEmptyDOMElement();
  });

  it("no tiene violaciones de accesibilidad con figura presente", async () => {
    const { container } = render(
      <ExerciseIllustration
        illustration_ascii={ASCII_FIGURE}
        illustration_alt={ALT_TEXT}
      />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad con alt de fallback", async () => {
    const { container } = render(
      <ExerciseIllustration illustration_ascii={ASCII_FIGURE} illustration_alt="" />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad cuando no hay figura (nada renderizado)", async () => {
    const { container } = render(
      <ExerciseIllustration illustration_ascii="" illustration_alt={ALT_TEXT} />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });
});
