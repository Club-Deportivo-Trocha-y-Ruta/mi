import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { Inbox } from "lucide-react";
import { EmptyState } from "../EmptyState";

describe("EmptyState", () => {
  // -------------------------------------------------------------------------
  // Título (siempre presente)
  // -------------------------------------------------------------------------
  describe("título", () => {
    it("siempre renderiza el título", () => {
      render(<EmptyState title="No hay datos" />);
      expect(screen.getByText("No hay datos")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Ícono opcional
  // -------------------------------------------------------------------------
  describe("ícono opcional", () => {
    it("no renderiza ícono cuando no se pasa", () => {
      const { container } = render(<EmptyState title="No hay datos" />);
      expect(container.querySelector("svg")).not.toBeInTheDocument();
    });

    it("renderiza el ícono cuando se pasa", () => {
      const { container } = render(<EmptyState title="No hay datos" icon={Inbox} />);
      expect(container.querySelector("svg")).toBeInTheDocument();
    });

    it("marca el ícono como decorativo (aria-hidden)", () => {
      const { container } = render(<EmptyState title="No hay datos" icon={Inbox} />);
      expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    });
  });

  // -------------------------------------------------------------------------
  // Descripción opcional
  // -------------------------------------------------------------------------
  describe("descripción opcional", () => {
    it("no renderiza descripción cuando no se pasa", () => {
      render(<EmptyState title="No hay datos" />);
      expect(screen.queryByText("Detalle adicional")).not.toBeInTheDocument();
    });

    it("renderiza la descripción cuando se pasa", () => {
      render(<EmptyState title="No hay datos" description="Detalle adicional" />);
      expect(screen.getByText("Detalle adicional")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Acción opcional
  // -------------------------------------------------------------------------
  describe("acción opcional", () => {
    it("no renderiza acción cuando no se pasa", () => {
      render(<EmptyState title="No hay datos" />);
      expect(screen.queryByRole("button")).not.toBeInTheDocument();
    });

    it("renderiza la acción cuando se pasa", () => {
      render(
        <EmptyState
          title="No hay datos"
          action={<button type="button">Crear nuevo</button>}
        />,
      );
      expect(screen.getByRole("button", { name: "Crear nuevo" })).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad (jest-axe)
  // -------------------------------------------------------------------------
  describe("accesibilidad", () => {
    it("no introduce violaciones con solo el título", async () => {
      const { container } = render(<EmptyState title="No hay datos" />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no introduce violaciones con todos los props presentes", async () => {
      const { container } = render(
        <EmptyState
          title="No hay competencias en esta temporada"
          description="Ajusta los filtros o crea la primera válida."
          icon={Inbox}
          action={<button type="button">+ Crear primera válida</button>}
        />,
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
