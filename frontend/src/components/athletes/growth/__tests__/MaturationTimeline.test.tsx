/**
 * Tests — MaturationTimeline (feature 040, US5, T066).
 *
 * Contrato: `specs/040-growth-module-redesign/contracts/growth-tab-ui.md`
 * (§Component tree, §Copy, §Accessibility, §Test ids `growth-timeline`).
 * Cubre: las tres etapas, el marcador de "hoy" recortado (clamp) al
 * dominio [-3, +3] años a partir de `maturity_offset`, el caption con
 * offset + edad de PHV, y la alternativa textual (role="img" + aria-label).
 *
 * Privacidad Ley 1581: props 100% sintéticas, sin datos de un atleta real.
 */
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { MaturationTimeline } from "@/components/athletes/growth/MaturationTimeline";
import { MaturationStatus } from "@/types/enums";

describe("MaturationTimeline", () => {
  it('expone data-testid="growth-timeline" en la raíz', () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PostPHV} maturityOffset={1.2} ageAtPhv={12.9} />,
    );
    expect(screen.getByTestId("growth-timeline")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Las tres etapas (copia exacta del contrato)
  // -------------------------------------------------------------------------

  it("renderiza las tres etapas del contrato: Pre-PHV, Estirón (Circa-PHV), Post-PHV", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.CircaPHV} maturityOffset={0} ageAtPhv={12.5} />,
    );
    expect(screen.getByText("Pre-PHV")).toBeInTheDocument();
    expect(screen.getByText("Estirón (Circa-PHV)")).toBeInTheDocument();
    expect(screen.getByText("Post-PHV")).toBeInTheDocument();
  });

  it.each([
    [MaturationStatus.PrePHV, "Pre-PHV"],
    [MaturationStatus.CircaPHV, "Estirón (Circa-PHV)"],
    [MaturationStatus.PostPHV, "Post-PHV"],
  ])("resalta la etapa activa (%s) sin depender sólo del color", (stage, label) => {
    const { container } = render(
      <MaturationTimeline stage={stage} maturityOffset={0} ageAtPhv={12.5} />,
    );
    const activeSegment = container.querySelector('[data-active="true"]');
    expect(activeSegment).toHaveTextContent(label);
    // El resto de las etapas no quedan marcadas como activas.
    expect(container.querySelectorAll('[data-active="true"]')).toHaveLength(1);
  });

  // -------------------------------------------------------------------------
  // Marcador de "hoy" — posición desde maturity_offset, recortada a [-3, +3]
  // -------------------------------------------------------------------------

  it("ubica el marcador de hoy al centro de la barra cuando el offset es 0", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.CircaPHV} maturityOffset={0} ageAtPhv={12.5} />,
    );
    const marker = screen.getByTestId("growth-timeline-marker");
    expect(marker).toHaveStyle({ left: "50%" });
  });

  it("ubica el marcador dentro del tercio Pre-PHV para un offset de -2 años", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PrePHV} maturityOffset={-2} ageAtPhv={13.1} />,
    );
    const marker = screen.getByTestId("growth-timeline-marker");
    // (-2 - (-3)) / 6 * 100 ≈ 16.67% — dentro del primer tercio (0-33.3%).
    const percent = parseFloat(marker.style.left);
    expect(percent).toBeGreaterThan(0);
    expect(percent).toBeLessThan(100 / 3);
  });

  it("ubica el marcador dentro del tercio Post-PHV para un offset de +2 años", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PostPHV} maturityOffset={2} ageAtPhv={12.1} />,
    );
    const marker = screen.getByTestId("growth-timeline-marker");
    const percent = parseFloat(marker.style.left);
    expect(percent).toBeGreaterThan((100 * 2) / 3);
    expect(percent).toBeLessThan(100);
  });

  it("recorta (clamp) un offset menor a -3 al extremo izquierdo (0%)", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PrePHV} maturityOffset={-8} ageAtPhv={14} />,
    );
    expect(screen.getByTestId("growth-timeline-marker")).toHaveStyle({ left: "0%" });
  });

  it("recorta (clamp) un offset mayor a +3 al extremo derecho (100%)", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PostPHV} maturityOffset={8} ageAtPhv={11} />,
    );
    expect(screen.getByTestId("growth-timeline-marker")).toHaveStyle({ left: "100%" });
  });

  it("no renderiza el marcador cuando aún no hay etapa/offset (sin mediciones)", () => {
    render(<MaturationTimeline stage={null} maturityOffset={null} ageAtPhv={null} />);
    expect(screen.queryByTestId("growth-timeline-marker")).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Caption — "Offset {±x.x} · PHV estimado a los {age} años"
  // -------------------------------------------------------------------------

  it("muestra el caption con offset positivo y edad de PHV", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PostPHV} maturityOffset={1.2} ageAtPhv={12.9} />,
    );
    expect(
      screen.getByText("Offset +1.2 · PHV estimado a los 12.9 años"),
    ).toBeInTheDocument();
  });

  it("muestra el caption con offset negativo (signo explícito)", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PrePHV} maturityOffset={-1.5} ageAtPhv={13.4} />,
    );
    expect(
      screen.getByText("Offset -1.5 · PHV estimado a los 13.4 años"),
    ).toBeInTheDocument();
  });

  it("muestra el caption con offset cero como '+0.0' (signo siempre explícito)", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.CircaPHV} maturityOffset={0} ageAtPhv={12.5} />,
    );
    expect(
      screen.getByText("Offset +0.0 · PHV estimado a los 12.5 años"),
    ).toBeInTheDocument();
  });

  it("sin mediciones, muestra un caption orientativo en vez del offset", () => {
    render(<MaturationTimeline stage={null} maturityOffset={null} ageAtPhv={null} />);
    expect(
      screen.getByText("Se necesitan más mediciones para ubicar el PHV en la línea de tiempo."),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Offset/)).not.toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Alternativa textual — role="img" + aria-label (nunca sólo la barra)
  // -------------------------------------------------------------------------

  it("expone role=img con un aria-label que resume etapa, offset y edad de PHV", () => {
    render(
      <MaturationTimeline stage={MaturationStatus.PostPHV} maturityOffset={1.2} ageAtPhv={12.9} />,
    );
    const img = screen.getByRole("img");
    expect(img).toHaveAccessibleName(/Post-PHV/);
    expect(img).toHaveAccessibleName(/\+1\.2/);
    expect(img).toHaveAccessibleName(/12\.9/);
  });

  it("expone un aria-label orientativo cuando aún no hay mediciones", () => {
    render(<MaturationTimeline stage={null} maturityOffset={null} ageAtPhv={null} />);
    expect(
      screen.getByRole("img", { name: /aún no hay mediciones suficientes/i }),
    ).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Accesibilidad (axe) — con y sin mediciones
  // -------------------------------------------------------------------------

  it("sin violaciones de accesibilidad (axe) con mediciones", async () => {
    const { container } = render(
      <MaturationTimeline stage={MaturationStatus.CircaPHV} maturityOffset={0.4} ageAtPhv={12.6} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("sin violaciones de accesibilidad (axe) sin mediciones", async () => {
    const { container } = render(
      <MaturationTimeline stage={null} maturityOffset={null} ageAtPhv={null} />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
