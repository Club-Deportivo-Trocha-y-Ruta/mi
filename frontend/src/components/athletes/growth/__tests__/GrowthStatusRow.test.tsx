import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { GrowthStatusRow } from "@/components/athletes/growth/GrowthStatusRow";
import { makeGrowthSummary } from "@/test/msw/growthSummaryHandlers";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// ---------------------------------------------------------------------------
// Fixtures — ficticias, sin datos reales de atletas.
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: 1,
    athlete_id: 2,
    evaluation_date: "2026-08-14",
    weight_kg: 45.0,
    standing_height_cm: 150.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 72.0,
    leg_sitting_ratio: 0.923,
    maturity_offset: 1.2,
    age_at_phv: 12.9,
    maturation_status: MaturationStatus.PostPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-08-14T10:00:00",
    notes: null,
    height_z_score: -1.66,
    height_percentile: 4.8,
    bmi: 21.9,
    bmi_z_score: 0.7,
    bmi_percentile: 75.7,
    weight_z_score: null,
    weight_percentile: null,
    nutritional_status: "adecuado",
    growth_source: "WHO",
    ...overrides,
  };
}

describe("GrowthStatusRow", () => {
  it("expone data-testid=growth-status-row en la raíz", () => {
    render(<GrowthStatusRow summary={makeGrowthSummary()} records={[makeRecord()]} />);
    expect(screen.getByTestId("growth-status-row")).toBeInTheDocument();
  });

  it("renderiza las cuatro etiquetas de tile exigidas por el contrato", () => {
    render(<GrowthStatusRow summary={makeGrowthSummary()} records={[makeRecord()]} />);
    expect(screen.getByText("Etapa")).toBeInTheDocument();
    expect(screen.getByText("Velocidad de talla")).toBeInTheDocument();
    expect(screen.getByText("Talla para la edad")).toBeInTheDocument();
    expect(screen.getByText("IMC para la edad")).toBeInTheDocument();
  });

  // -------------------------------------------------------------------------
  // Tile "Etapa"
  // -------------------------------------------------------------------------
  describe("tile Etapa", () => {
    it("muestra la etapa y hace cuántos meses fue el PHV cuando ya pasó", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({ stage: MaturationStatus.PostPHV, months_from_phv: 16.4 })}
          records={[makeRecord()]}
        />,
      );
      expect(screen.getByText("Post-PHV")).toBeInTheDocument();
      expect(screen.getByText(/PHV estimado a los 12.9 años/)).toBeInTheDocument();
      expect(screen.getByText(/hace 16 meses/)).toBeInTheDocument();
    });

    it("muestra 'en N meses' cuando el PHV todavía no ocurre (months_from_phv negativo)", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({ stage: MaturationStatus.PrePHV, months_from_phv: -5.2 })}
          records={[makeRecord()]}
        />,
      );
      expect(screen.getByText(/en 5 meses/)).toBeInTheDocument();
    });

    it("muestra un guion cuando no hay etapa (sin mediciones)", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({ stage: null, age_at_phv: null, months_from_phv: null })}
          records={[]}
        />,
      );
      expect(screen.getAllByText("—").length).toBeGreaterThan(0);
    });

    it("no colorea la etapa (D2/Removed — sin mapa de color por fase PHV)", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({ stage: MaturationStatus.CircaPHV })}
          records={[makeRecord()]}
        />,
      );
      // El tile de Etapa (el propio Card, identificado por su label) nunca
      // lleva acento de borde por tono — a diferencia de los tiles de banda,
      // que sí pueden traerlo (ver fixture: talla en "riesgo_retraso_talla").
      const etapaCard = screen.getByText("Etapa").closest(".shadow-card");
      expect(etapaCard).not.toHaveClass("border-l-warning");
      expect(etapaCard).not.toHaveClass("border-l-danger");
    });
  });

  // -------------------------------------------------------------------------
  // Tile "Velocidad de talla"
  // -------------------------------------------------------------------------
  describe("tile Velocidad de talla", () => {
    it("pide dos mediciones cuando la velocidad es null", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({ velocity: null })}
          records={[makeRecord()]}
        />,
      );
      expect(screen.getByText("Se necesitan 2 mediciones")).toBeInTheDocument();
    });

    it("muestra cm/año, ventana en meses y el rango esperado", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({
            velocity: {
              cm_per_month: 0.31,
              cm_per_year: 3.7,
              window_days: 101,
              interval_short: false,
              expected_cm_per_year: [1.0, 4.0],
            },
          })}
          records={[makeRecord(), makeRecord({ id: 2, evaluation_date: "2026-05-05" })]}
        />,
      );
      expect(screen.getByText("3.7 cm/año")).toBeInTheDocument();
      expect(screen.getByText(/últimos 3 meses/)).toBeInTheDocument();
      expect(screen.getByText(/esperado 1–4 cm\/año \(orientativo\)/)).toBeInTheDocument();
    });

    it("agrega la advertencia de intervalo corto cuando interval_short es true", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({
            velocity: {
              cm_per_month: 0.5,
              cm_per_year: 6.0,
              window_days: 20,
              interval_short: true,
              expected_cm_per_year: [1.0, 4.0],
            },
          })}
          records={[makeRecord(), makeRecord({ id: 2 })]}
        />,
      );
      expect(screen.getByText(/Intervalo corto: valor orientativo/)).toBeInTheDocument();
    });

    it("muestra una insignia de advertencia cuando la alerta rapid_growth está presente", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({
            alerts: ["rapid_growth"],
            velocity: {
              cm_per_month: 0.7,
              cm_per_year: 8.4,
              window_days: 60,
              interval_short: false,
              expected_cm_per_year: [1.0, 4.0],
            },
          })}
          records={[makeRecord(), makeRecord({ id: 2 })]}
        />,
      );
      expect(screen.getByText("Crecimiento rápido")).toBeInTheDocument();
    });

    it("renderiza el sparkline de tendencia sólo cuando hay 2 o más mediciones", () => {
      // El sparkline es el único svg con role="img" de la fila — los íconos
      // de StatusBadge son decorativos (aria-hidden, sin role).
      const { container, rerender } = render(
        <GrowthStatusRow summary={makeGrowthSummary({ velocity: null })} records={[makeRecord()]} />,
      );
      expect(container.querySelector('svg[role="img"]')).not.toBeInTheDocument();

      rerender(
        <GrowthStatusRow
          summary={makeGrowthSummary()}
          records={[makeRecord(), makeRecord({ id: 2, standing_height_cm: 148 })]}
        />,
      );
      expect(container.querySelector('svg[role="img"]')).toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Tiles de banda (Talla / IMC para la edad)
  // -------------------------------------------------------------------------
  describe("tiles de banda", () => {
    it("muestra percentil, Z-score e insignia de la banda de talla", () => {
      render(<GrowthStatusRow summary={makeGrowthSummary()} records={[makeRecord()]} />);
      expect(screen.getByText("P5 · Z -1.66")).toBeInTheDocument();
      expect(screen.getByText("En vigilancia")).toBeInTheDocument();
    });

    it("muestra percentil, Z-score e insignia de la banda de IMC", () => {
      render(<GrowthStatusRow summary={makeGrowthSummary()} records={[makeRecord()]} />);
      expect(screen.getByText("P76 · Z 0.70")).toBeInTheDocument();
      expect(screen.getByText("Adecuado")).toBeInTheDocument();
    });

    it("muestra la referencia OMS 2007 cuando growth_source es WHO", () => {
      render(<GrowthStatusRow summary={makeGrowthSummary()} records={[makeRecord()]} />);
      expect(screen.getAllByText("OMS 2007 · Res. 2465/2016").length).toBeGreaterThan(0);
    });

    it("muestra el aviso de referencia anterior cuando growth_source no es WHO", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({
            latest: {
              record_id: 41,
              growth_source: null,
              height: { value: 150, z_score: -1.66, percentile: 4.8, band: "riesgo_retraso_talla" },
              bmi: { value: 21.9, z_score: 0.7, percentile: 75.7, band: "adecuado" },
              weight: null,
            },
          })}
          records={[makeRecord()]}
        />,
      );
      expect(
        screen.getAllByText("Referencia anterior — pendiente de actualizar").length,
      ).toBeGreaterThan(0);
    });

    it("muestra un guion cuando no hay referencia de talla para la edad", () => {
      render(
        <GrowthStatusRow
          summary={makeGrowthSummary({
            latest: {
              record_id: 41,
              growth_source: "WHO",
              height: null,
              bmi: { value: 21.9, z_score: 0.7, percentile: 75.7, band: "adecuado" },
              weight: null,
            },
          })}
          records={[makeRecord()]}
        />,
      );
      expect(screen.getByText("Sin referencia para la edad")).toBeInTheDocument();
    });
  });

  it("sin violaciones de accesibilidad (axe) con datos completos", async () => {
    const { container } = render(
      <GrowthStatusRow
        summary={makeGrowthSummary()}
        records={[makeRecord(), makeRecord({ id: 2, evaluation_date: "2026-05-05" })]}
      />,
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
