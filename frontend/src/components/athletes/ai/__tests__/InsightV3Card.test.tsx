/**
 * InsightV3Card — feature 037, T301.
 *
 * Cubre: render de todos los bloques (coach), gating de bloques
 * coach-only en mode="parent", aviso de fallback (isFallback=true, no
 * lee trend/field_reading), slot `footer`, y cero violaciones jest-axe.
 */
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { InsightV3Card } from "@/components/athletes/ai/v3/InsightV3Card";
import { buildInsightV3 } from "@/test/fixtures/insightV3";

describe("InsightV3Card", () => {
  it("renderiza titular, lectura del pelotón, observaciones, acciones, señales y pregunta (mode=coach)", () => {
    const structured = buildInsightV3();
    render(
      <InsightV3Card
        structured={structured}
        mode="coach"
        footer={<div data-testid="coach-answer-slot">form</div>}
      />,
    );

    expect(screen.getByTestId("insight-v3-headline")).toHaveTextContent(
      structured.headline,
    );
    expect(screen.getByTestId("insight-v3-field-reading")).toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-percentile-chip")).toHaveTextContent(
      "Percentil 63",
    );
    // Esperado vs real SÍ se muestra en modo coach.
    expect(screen.getByTestId("insight-v3-delta-chip")).toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-observation-0")).toHaveTextContent(
      structured.observations[0].claim,
    );
    expect(screen.getByTestId("insight-v3-action-0")).toHaveTextContent(
      structured.actions[0].text,
    );
    expect(screen.getByTestId("insight-v3-watch-signal-0")).toHaveTextContent(
      structured.watch_signals[0],
    );
    expect(screen.getByTestId("insight-v3-coach-question")).toHaveTextContent(
      structured.coach_question,
    );
    expect(screen.getByTestId("coach-answer-slot")).toBeInTheDocument();
  });

  it("mode=parent oculta esperado-vs-real, pregunta del coach, footer y evidencia de dominio training", () => {
    const structured = buildInsightV3();
    render(
      <InsightV3Card
        structured={structured}
        mode="parent"
        footer={<div data-testid="coach-answer-slot">form</div>}
      />,
    );

    // El percentil/serie sigue visible en modo parent.
    expect(screen.getByTestId("insight-v3-field-reading")).toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-percentile-chip")).toBeInTheDocument();
    // Esperado vs real NO se muestra en modo parent.
    expect(screen.queryByTestId("insight-v3-delta-chip")).not.toBeInTheDocument();
    // La pregunta del coach (+ footer) no se renderiza en modo parent.
    expect(screen.queryByTestId("insight-v3-coach-question")).not.toBeInTheDocument();
    expect(screen.queryByTestId("coach-answer-slot")).not.toBeInTheDocument();
    // La observación de dominio "training" se filtra en modo parent.
    expect(
      screen.queryByText(structured.observations[1].claim),
    ).not.toBeInTheDocument();
    expect(screen.getByText(structured.observations[0].claim)).toBeInTheDocument();
  });

  it("isFallback=true muestra el aviso de fallback sin leer trend ni field_reading", () => {
    const structured = buildInsightV3();
    render(
      <InsightV3Card structured={structured} mode="coach" isFallback />,
    );

    expect(screen.getByTestId("insight-fallback-notice")).toBeInTheDocument();
    expect(screen.queryByTestId("insight-v3-headline")).not.toBeInTheDocument();
    expect(screen.queryByTestId("insight-v3-field-reading")).not.toBeInTheDocument();
  });

  it("tolera field_reading null (resumen de temporada primer año)", () => {
    const structured = buildInsightV3({ field_reading: null });
    render(<InsightV3Card structured={structured} mode="coach" />);

    expect(screen.queryByTestId("insight-v3-field-reading")).not.toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-headline")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad (mode=coach)", async () => {
    const structured = buildInsightV3();
    const { container } = render(
      <InsightV3Card
        structured={structured}
        mode="coach"
        footer={<button type="button">Guardar</button>}
      />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones de accesibilidad (mode=parent)", async () => {
    const structured = buildInsightV3();
    const { container } = render(
      <InsightV3Card structured={structured} mode="parent" />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
