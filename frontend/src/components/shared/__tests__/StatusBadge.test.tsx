import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { Info } from "lucide-react";
import { StatusBadge, type Status } from "../StatusBadge";

expect.extend(toHaveNoViolations);

const STATUSES: Status[] = ["success", "warning", "danger", "neutral"];

describe("StatusBadge", () => {
  // -------------------------------------------------------------------------
  // Label + ícono siempre presentes (constitution III — color nunca es el
  // único canal)
  // -------------------------------------------------------------------------
  describe.each(STATUSES)("status=%s", (status) => {
    const label = `Etiqueta ${status}`;

    it("renderiza el texto de la etiqueta", () => {
      render(<StatusBadge status={status} label={label} />);
      expect(screen.getByText(label)).toBeInTheDocument();
    });

    it("renderiza un ícono (svg)", () => {
      const { container } = render(<StatusBadge status={status} label={label} />);
      expect(container.querySelector("svg")).toBeInTheDocument();
    });

    it("marca el ícono como decorativo (aria-hidden) ya que el texto ya lo describe", () => {
      const { container } = render(<StatusBadge status={status} label={label} />);
      expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
    });

    it("sin violaciones de accesibilidad (axe)", async () => {
      const { container } = render(<StatusBadge status={status} label={label} />);
      expect(await axe(container)).toHaveNoViolations();
    });
  });

  // -------------------------------------------------------------------------
  // Ícono custom
  // -------------------------------------------------------------------------
  describe("ícono personalizado", () => {
    it("usa el ícono pasado en vez del default", () => {
      const { container } = render(
        <StatusBadge status="success" label="Con ícono custom" icon={Info} />,
      );
      // lucide-react renders a distinctive class per icon; Info's default
      // CheckCircle2 svg would not carry this class.
      const svg = container.querySelector("svg");
      expect(svg).toBeInTheDocument();
      expect(svg).toHaveClass("lucide-info");
    });

    it("sin violaciones de accesibilidad con ícono custom", async () => {
      const { container } = render(
        <StatusBadge status="danger" label="Con ícono custom" icon={Info} />,
      );
      expect(await axe(container)).toHaveNoViolations();
    });
  });
});
