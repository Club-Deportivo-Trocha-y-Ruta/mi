import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionStatusBadge, sessionStatus } from "./SessionStatusBadge";
import type { SessionStatus } from "@/types/trainingSession.types";

describe("SessionStatusBadge", () => {
  it("muestra 'Planificada' para status planned", () => {
    render(<SessionStatusBadge status="planned" />);
    expect(screen.getByText("Planificada")).toBeInTheDocument();
  });

  it("muestra 'Ejecutada' para status executed", () => {
    render(<SessionStatusBadge status="executed" />);
    expect(screen.getByText("Ejecutada")).toBeInTheDocument();
  });

  it("muestra 'Cancelada' para status cancelled", () => {
    render(<SessionStatusBadge status="cancelled" />);
    expect(screen.getByText("Cancelada")).toBeInTheDocument();
  });

  it("renderiza vía StatusBadge — tono success (bg-success/10) para executed", () => {
    render(<SessionStatusBadge status="executed" />);
    const badge = screen.getByText("Ejecutada").closest("span");
    expect(badge).toHaveClass("bg-success/10");
  });

  it("renderiza vía StatusBadge — tono danger (bg-danger/10) para cancelled", () => {
    render(<SessionStatusBadge status="cancelled" />);
    const badge = screen.getByText("Cancelada").closest("span");
    expect(badge).toHaveClass("bg-danger/10");
  });

  it("renderiza vía StatusBadge — tono neutral (bg-light-gray) para planned", () => {
    render(<SessionStatusBadge status="planned" />);
    const badge = screen.getByText("Planificada").closest("span");
    expect(badge).toHaveClass("bg-light-gray");
  });

  // Regresión (contract §"Test obligations"): SessionStatusBadge ya no debe
  // renderizar el <span data-status> artesanal con className manual — todo
  // pasa por <StatusBadge> (ícono + label siempre juntos).
  it("no renderiza un <span data-status> artesanal — solo el StatusBadge compartido", () => {
    const { container } = render(<SessionStatusBadge status="executed" />);
    expect(container.querySelector("[data-status]")).not.toBeInTheDocument();
    // StatusBadge siempre pairea el label con un ícono (Constitution III).
    expect(container.querySelector("svg")).toBeInTheDocument();
  });
});

describe("sessionStatus adapter", () => {
  it.each<[SessionStatus, { status: string; label: string }]>([
    ["planned", { status: "neutral", label: "Planificada" }],
    ["executed", { status: "success", label: "Ejecutada" }],
    ["cancelled", { status: "danger", label: "Cancelada" }],
  ])("%s → %o", (status, expected) => {
    expect(sessionStatus(status)).toEqual(expected);
  });
});
