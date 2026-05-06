import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { SessionStatusBadge } from "./SessionStatusBadge";

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

  it("aplica clase verde para executed", () => {
    const { container } = render(<SessionStatusBadge status="executed" />);
    const badge = container.querySelector("[data-status='executed']");
    expect(badge?.className).toContain("green");
  });

  it("aplica clase roja para cancelled", () => {
    const { container } = render(<SessionStatusBadge status="cancelled" />);
    const badge = container.querySelector("[data-status='cancelled']");
    expect(badge?.className).toContain("red");
  });

  it("aplica clase gris para planned", () => {
    const { container } = render(<SessionStatusBadge status="planned" />);
    const badge = container.querySelector("[data-status='planned']");
    expect(badge?.className).toContain("light-gray");
  });
});
