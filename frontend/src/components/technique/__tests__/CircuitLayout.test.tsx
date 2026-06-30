/**
 * Tests para CircuitLayout (T023 — criterio de aceptación T021).
 *
 * Cubre:
 *  - El bloque <pre> tiene role="img" y aria-label igual a layout_alt.
 *  - El <VisuallyHidden> repite layout_alt como texto visible para SRs.
 *  - La leyenda del circuito se renderiza cuando hay layout.
 *  - No renders para ejercicio no-gymkhana.
 *  - No renders para gymkhana con layout_ascii null / vacío.
 *  - Zero violaciones de accesibilidad (jest-axe).
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { CircuitLayout } from "../CircuitLayout";
import type { ExerciseDetail } from "@/types/technique.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BASE_EXERCISE: ExerciseDetail = {
  id: 1,
  slug: "gymkhana-basica-ficticia",
  name: "Gymkhana Básica Ficticia",
  summary: "Circuito de prueba — datos ficticios.",
  difficulty: "facil",
  is_game: false,
  is_gymkhana: true,
  age_bands: ["10-12"],
  skills: [{ code: "EQ", slug: "equilibrio", name: "Equilibrio" }],
  materials: [{ slug: "conos", name: "Conos", is_none: false }],
  is_seeded: true,
  is_hidden: false,
  how_to: "Rodea los conos ficticio.",
  layout_ascii:
    "S --> [ ] --> ( ) --> F",
  layout_alt: "Circuito de gymkhana: Salida, dos obstáculos, llegada.",
  layout_json: null,
  confidence: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function gymkhana(overrides?: Partial<ExerciseDetail>) {
  return { ...BASE_EXERCISE, ...overrides };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("CircuitLayout", () => {
  describe("cuando el ejercicio es gymkhana con layout_ascii", () => {
    it("renderiza el <pre> con role='img'", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      // El pre tiene role="img" según la implementación (WCAG 1.1.1)
      const diagram = screen.getByRole("img");
      expect(diagram.tagName).toBe("PRE");
    });

    it("aria-label del <pre> coincide con layout_alt", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      const diagram = screen.getByRole("img");
      expect(diagram).toHaveAttribute(
        "aria-label",
        "Circuito de gymkhana: Salida, dos obstáculos, llegada.",
      );
    });

    it("el texto alternativo está presente en el DOM para SRs que ignoran role='img'", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      // VisuallyHidden renderiza el texto dentro del <pre> — debe existir en el DOM
      // aunque esté visualmente oculto.
      expect(
        screen.getByText(
          "Circuito de gymkhana: Salida, dos obstáculos, llegada.",
        ),
      ).toBeInTheDocument();
    });

    it("el <pre> contiene el layout_ascii", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      const diagram = screen.getByRole("img");
      expect(diagram.textContent).toContain("S --> [ ] --> ( ) --> F");
    });

    it("renderiza la leyenda con los símbolos del circuito", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      // Presencia del encabezado de la leyenda
      expect(screen.getByText("Leyenda del circuito")).toBeInTheDocument();
      // Verificar al menos un símbolo conocido de la leyenda seeded
      expect(screen.getByText("Inicio / Salida")).toBeInTheDocument();
      expect(screen.getByText("Llegada / Fin")).toBeInTheDocument();
    });

    it("la sección tiene aria-label='Circuito y leyenda'", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      const section = screen.getByRole("region", {
        name: "Circuito y leyenda",
      });
      expect(section).toBeInTheDocument();
    });

    it("usa el texto de fallback cuando layout_alt es null", () => {
      render(<CircuitLayout exercise={gymkhana({ layout_alt: null })} />);
      const diagram = screen.getByRole("img");
      expect(diagram).toHaveAttribute(
        "aria-label",
        "Diagrama del circuito de gymkhana",
      );
    });

    it("usa el texto de fallback cuando layout_alt es cadena vacía", () => {
      render(<CircuitLayout exercise={gymkhana({ layout_alt: "" })} />);
      const diagram = screen.getByRole("img");
      expect(diagram).toHaveAttribute(
        "aria-label",
        "Diagrama del circuito de gymkhana",
      );
    });

    it("no tiene violaciones de accesibilidad", async () => {
      const { container } = render(<CircuitLayout exercise={gymkhana()} />);
      expect(await axe(container)).toHaveNoViolations();
    });
  });

  describe("cuando el ejercicio NO debe renderizar el circuito", () => {
    it("retorna null para ejercicio no-gymkhana (is_gymkhana=false)", () => {
      const { container } = render(
        <CircuitLayout exercise={gymkhana({ is_gymkhana: false })} />,
      );
      expect(container).toBeEmptyDOMElement();
    });

    it("retorna null para gymkhana con layout_ascii null", () => {
      const { container } = render(
        <CircuitLayout
          exercise={gymkhana({ is_gymkhana: true, layout_ascii: null })}
        />,
      );
      expect(container).toBeEmptyDOMElement();
    });

    it("retorna null para gymkhana con layout_ascii de solo espacios", () => {
      const { container } = render(
        <CircuitLayout
          exercise={gymkhana({ is_gymkhana: true, layout_ascii: "   " })}
        />,
      );
      expect(container).toBeEmptyDOMElement();
    });

    it("no tiene violaciones de accesibilidad cuando retorna null", async () => {
      const { container } = render(
        <CircuitLayout exercise={gymkhana({ is_gymkhana: false })} />,
      );
      expect(await axe(container)).toHaveNoViolations();
    });
  });

  describe("leyenda", () => {
    it("muestra los siete símbolos definidos", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      const legend = screen.getByRole("list");
      const items = within(legend).getAllByRole("listitem");
      // Los símbolos definidos en CircuitLegend son 7
      expect(items).toHaveLength(7);
    });

    it("incluye el símbolo de trayecto técnico", () => {
      render(<CircuitLayout exercise={gymkhana()} />);
      expect(
        screen.getByText("Trayecto técnico (precisión)"),
      ).toBeInTheDocument();
    });
  });
});
