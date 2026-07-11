import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { PHVBadge } from "./PHVBadge";
import { MaturationStatus } from "@/types/enums";

describe("PHVBadge", () => {
  // -------------------------------------------------------------------------
  // Renderizado de texto
  // -------------------------------------------------------------------------
  describe("cuando se renderiza con un estado de maduración", () => {
    it("debería mostrar 'Pre-PHV' cuando status = PrePHV", () => {
      render(<PHVBadge status={MaturationStatus.PrePHV} />);
      expect(screen.getByText("Pre-PHV")).toBeInTheDocument();
    });

    it("debería mostrar 'Circa-PHV' cuando status = CircaPHV", () => {
      render(<PHVBadge status={MaturationStatus.CircaPHV} />);
      expect(screen.getByText("Circa-PHV")).toBeInTheDocument();
    });

    it("debería mostrar 'Post-PHV' cuando status = PostPHV", () => {
      render(<PHVBadge status={MaturationStatus.PostPHV} />);
      expect(screen.getByText("Post-PHV")).toBeInTheDocument();
    });

    it("debería mostrar 'Sin evaluar' cuando status = null", () => {
      render(<PHVBadge status={null} />);
      expect(screen.getByText("Sin evaluar")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Clases de color correctas
  // -------------------------------------------------------------------------
  describe("cuando se aplican clases de color", () => {
    it("debería aplicar clases azul (blue) para Pre-PHV", () => {
      render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const badge = screen.getByText("Pre-PHV");
      expect(badge.className).toContain("bg-blue-100");
      expect(badge.className).toContain("text-blue-700");
    });

    it("debería aplicar clases ámbar (amber) para Circa-PHV", () => {
      render(<PHVBadge status={MaturationStatus.CircaPHV} />);
      const badge = screen.getByText("Circa-PHV");
      expect(badge.className).toContain("bg-amber-100");
      expect(badge.className).toContain("text-amber-700");
    });

    it("debería aplicar clases verde (green) para Post-PHV", () => {
      render(<PHVBadge status={MaturationStatus.PostPHV} />);
      const badge = screen.getByText("Post-PHV");
      expect(badge.className).toContain("bg-green-100");
      expect(badge.className).toContain("text-green-700");
    });

    it("debería aplicar clases slate para estado null (Sin evaluar)", () => {
      render(<PHVBadge status={null} />);
      const badge = screen.getByText("Sin evaluar");
      expect(badge.className).toContain("bg-light-gray");
      expect(badge.className).toContain("text-mid-gray");
    });
  });

  // -------------------------------------------------------------------------
  // Tamaños
  // -------------------------------------------------------------------------
  describe("cuando se aplica el prop size", () => {
    it("debería usar clases sm por defecto", () => {
      render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const badge = screen.getByText("Pre-PHV");
      expect(badge.className).toContain("text-xs");
    });

    it("debería usar clases md cuando size='md'", () => {
      render(<PHVBadge status={MaturationStatus.PrePHV} size="md" />);
      const badge = screen.getByText("Pre-PHV");
      expect(badge.className).toContain("text-sm");
    });
  });

  // -------------------------------------------------------------------------
  // Estructura del elemento
  // -------------------------------------------------------------------------
  describe("estructura del componente", () => {
    it("debería renderizar como un elemento span", () => {
      render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const badge = screen.getByText("Pre-PHV");
      expect(badge.tagName).toBe("SPAN");
    });

    it("debería incluir las clases base de estilo en todos los estados", () => {
      const { rerender } = render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const baseClasses = ["inline-block", "rounded-full", "font-medium"];

      for (const status of [MaturationStatus.PrePHV, MaturationStatus.CircaPHV, MaturationStatus.PostPHV, null]) {
        rerender(<PHVBadge status={status} />);
        const text = status ?? "Sin evaluar";
        const badge = screen.getByText(text);
        for (const cls of baseClasses) {
          expect(badge.className).toContain(cls);
        }
      }
    });

    it("no debería renderizar nada vacío — siempre tiene texto", () => {
      render(<PHVBadge status={null} />);
      const badge = screen.getByText("Sin evaluar");
      expect(badge.textContent).toBeTruthy();
    });
  });

  // -------------------------------------------------------------------------
  // Variante: cada estado tiene un color exclusivo (no comparten clases de color)
  // -------------------------------------------------------------------------
  describe("cuando se comparan colores entre estados", () => {
    it("Pre-PHV y Post-PHV deberían tener clases de fondo distintas", () => {
      const { unmount } = render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const preBg = screen.getByText("Pre-PHV").className;
      unmount();

      render(<PHVBadge status={MaturationStatus.PostPHV} />);
      const postBg = screen.getByText("Post-PHV").className;

      expect(preBg).not.toBe(postBg);
    });

    it("Circa-PHV y Pre-PHV deberían tener clases de color distintas", () => {
      const { unmount } = render(<PHVBadge status={MaturationStatus.CircaPHV} />);
      const circaClasses = screen.getByText("Circa-PHV").className;
      unmount();

      render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const preClasses = screen.getByText("Pre-PHV").className;

      expect(circaClasses).not.toBe(preClasses);
    });
  });
});
