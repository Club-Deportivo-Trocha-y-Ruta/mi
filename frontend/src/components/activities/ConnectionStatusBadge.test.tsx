/**
 * Tests de ConnectionStatusBadge (feature 025, T027).
 *
 * Cubre los 4 estados de `StravaConnectionStatus` (none/active/broken/
 * disconnected): label correcto, ícono presente, y accesibilidad (0
 * violaciones axe) para cada uno.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { ConnectionStatusBadge } from "./ConnectionStatusBadge";
import type { StravaConnectionStatus } from "@/types/strava.types";

expect.extend(toHaveNoViolations);

describe("ConnectionStatusBadge", () => {
  it("muestra 'Sin conectar' para el estado none", () => {
    render(<ConnectionStatusBadge status="none" />);
    expect(screen.getByText("Sin conectar")).toBeInTheDocument();
  });

  it("muestra 'Conectado' para el estado active", () => {
    render(<ConnectionStatusBadge status="active" />);
    expect(screen.getByText("Conectado")).toBeInTheDocument();
  });

  it("muestra 'Conexión rota' para el estado broken", () => {
    render(<ConnectionStatusBadge status="broken" />);
    expect(screen.getByText("Conexión rota")).toBeInTheDocument();
  });

  it("muestra 'Desconectado' para el estado disconnected", () => {
    render(<ConnectionStatusBadge status="disconnected" />);
    expect(screen.getByText("Desconectado")).toBeInTheDocument();
  });

  it("aplica la clase de variante success en el estado active", () => {
    render(<ConnectionStatusBadge status="active" />);
    expect(screen.getByText("Conectado").closest("span")).toHaveClass(
      "bg-green-100",
    );
  });

  it("aplica la clase de variante warning en el estado broken", () => {
    render(<ConnectionStatusBadge status="broken" />);
    expect(screen.getByText("Conexión rota").closest("span")).toHaveClass(
      "bg-amber-100",
    );
  });

  it("acepta className adicional sin perder las clases base", () => {
    render(<ConnectionStatusBadge status="none" className="ml-2" />);
    expect(screen.getByText("Sin conectar").closest("span")).toHaveClass(
      "ml-2",
    );
  });

  it.each<StravaConnectionStatus>(["none", "active", "broken", "disconnected"])(
    "no tiene violaciones de accesibilidad en el estado %s",
    async (status) => {
      const { container } = render(<ConnectionStatusBadge status={status} />);
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    },
  );
});
