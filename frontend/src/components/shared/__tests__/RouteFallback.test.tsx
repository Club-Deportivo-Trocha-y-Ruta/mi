import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { RouteFallback } from "../RouteFallback";

describe("RouteFallback", () => {
  // -------------------------------------------------------------------------
  // Label
  // -------------------------------------------------------------------------
  describe("label", () => {
    it("renderiza el texto del label recibido", () => {
      render(<RouteFallback label="Cargando sesiones..." />);
      expect(screen.getByText("Cargando sesiones...")).toBeInTheDocument();
    });

    it("renderiza un label distinto sin dejar rastro del anterior", () => {
      const { rerender } = render(<RouteFallback label="Cargando asistente IA..." />);
      expect(screen.getByText("Cargando asistente IA...")).toBeInTheDocument();

      rerender(<RouteFallback label="Cargando comparación plan vs. real…" />);
      expect(screen.getByText("Cargando comparación plan vs. real…")).toBeInTheDocument();
      expect(screen.queryByText("Cargando asistente IA...")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Anuncio a lectores de pantalla
  // -------------------------------------------------------------------------
  describe("anuncio accesible", () => {
    it("expone role=status", () => {
      render(<RouteFallback label="Cargando sesiones..." />);
      expect(screen.getByRole("status")).toBeInTheDocument();
    });

    it("usa aria-live=polite en el mismo nodo que role=status", () => {
      render(<RouteFallback label="Cargando sesiones..." />);
      expect(screen.getByRole("status")).toHaveAttribute("aria-live", "polite");
    });
  });

  // -------------------------------------------------------------------------
  // Estilos (deben coincidir con el bloque duplicado en App.tsx)
  // -------------------------------------------------------------------------
  describe("estilos", () => {
    it("aplica las clases del fallback original de App.tsx", () => {
      render(<RouteFallback label="Cargando sesiones..." />);
      expect(screen.getByRole("status")).toHaveClass(
        "flex",
        "min-h-[40vh]",
        "items-center",
        "justify-center",
        "text-sm",
        "text-mid-gray",
      );
    });
  });

  // -------------------------------------------------------------------------
  // Accesibilidad (jest-axe)
  // -------------------------------------------------------------------------
  describe("accesibilidad", () => {
    it("no introduce violaciones", async () => {
      const { container } = render(<RouteFallback label="Cargando sesiones..." />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
