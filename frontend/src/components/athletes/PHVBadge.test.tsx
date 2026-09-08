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
  // Mapeo a StatusBadge (icono + color por estado, nunca solo color)
  // -------------------------------------------------------------------------
  describe("cuando se delega en StatusBadge", () => {
    it("Pre-PHV usa el tono neutral (bg-light-gray)", () => {
      render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const badge = screen.getByText("Pre-PHV").closest("span");
      expect(badge?.className).toContain("bg-light-gray");
    });

    it("Circa-PHV usa el tono warning", () => {
      render(<PHVBadge status={MaturationStatus.CircaPHV} />);
      const badge = screen.getByText("Circa-PHV").closest("span");
      expect(badge?.className).toContain("bg-warning/10");
    });

    it("Post-PHV usa el tono success", () => {
      render(<PHVBadge status={MaturationStatus.PostPHV} />);
      const badge = screen.getByText("Post-PHV").closest("span");
      expect(badge?.className).toContain("bg-success/10");
    });

    it("Sin evaluar (status null) usa el tono neutral", () => {
      render(<PHVBadge status={null} />);
      const badge = screen.getByText("Sin evaluar").closest("span");
      expect(badge?.className).toContain("bg-light-gray");
    });

    it("cada estado trae un ícono (nunca solo color)", () => {
      const { container } = render(<PHVBadge status={MaturationStatus.CircaPHV} />);
      expect(container.querySelector("svg")).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Tamaños
  // -------------------------------------------------------------------------
  describe("cuando se aplica el prop size", () => {
    it("no agrega clases de tamaño extra por defecto (sm)", () => {
      const { container } = render(<PHVBadge status={MaturationStatus.PrePHV} />);
      expect(container.firstElementChild?.className).not.toContain("text-sm");
    });

    it("agrega text-sm en el contenedor cuando size='md'", () => {
      const { container } = render(<PHVBadge status={MaturationStatus.PrePHV} size="md" />);
      expect(container.firstElementChild?.className).toContain("text-sm");
    });
  });

  // -------------------------------------------------------------------------
  // Variante: cada estado tiene un color exclusivo (no comparten clases de color)
  // -------------------------------------------------------------------------
  describe("cuando se comparan colores entre estados", () => {
    it("Pre-PHV y Post-PHV deberían tener clases de fondo distintas", () => {
      const { unmount } = render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const preBg = screen.getByText("Pre-PHV").closest("span")?.className;
      unmount();

      render(<PHVBadge status={MaturationStatus.PostPHV} />);
      const postBg = screen.getByText("Post-PHV").closest("span")?.className;

      expect(preBg).not.toBe(postBg);
    });

    it("Circa-PHV y Pre-PHV deberían tener clases de color distintas", () => {
      const { unmount } = render(<PHVBadge status={MaturationStatus.CircaPHV} />);
      const circaClasses = screen.getByText("Circa-PHV").closest("span")?.className;
      unmount();

      render(<PHVBadge status={MaturationStatus.PrePHV} />);
      const preClasses = screen.getByText("Pre-PHV").closest("span")?.className;

      expect(circaClasses).not.toBe(preClasses);
    });
  });
});
