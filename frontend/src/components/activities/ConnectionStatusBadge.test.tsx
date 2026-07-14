/**
 * Tests de ConnectionStatusBadge (feature 025, T027).
 *
 * Cubre los 4 estados de `StravaConnectionStatus` (none/active/broken/
 * disconnected): label correcto, ícono presente, y accesibilidad (0
 * violaciones axe) para cada uno.
 */
import { CheckCircle2, CircleOff, Link2Off, TriangleAlert } from "lucide-react";
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { ConnectionStatusBadge, connectionStatus } from "./ConnectionStatusBadge";
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

  it("renderiza vía StatusBadge — tono success en el estado active", () => {
    render(<ConnectionStatusBadge status="active" />);
    expect(screen.getByText("Conectado").closest("span")).toHaveClass(
      "bg-success/10",
    );
  });

  it("renderiza vía StatusBadge — tono warning en el estado broken", () => {
    render(<ConnectionStatusBadge status="broken" />);
    expect(screen.getByText("Conexión rota").closest("span")).toHaveClass(
      "bg-warning/10",
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

describe("connectionStatus adapter", () => {
  it.each<
    [StravaConnectionStatus, { status: string; label: string; icon: unknown }]
  >([
    ["none", { status: "neutral", label: "Sin conectar", icon: CircleOff }],
    ["active", { status: "success", label: "Conectado", icon: CheckCircle2 }],
    ["broken", { status: "warning", label: "Conexión rota", icon: TriangleAlert }],
    ["disconnected", { status: "neutral", label: "Desconectado", icon: Link2Off }],
  ])("mapea %s → %o", (state, expected) => {
    expect(connectionStatus(state)).toEqual(expected);
  });
});
