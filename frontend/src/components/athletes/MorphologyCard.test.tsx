import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MorphologyCard } from "./MorphologyCard";
import { MaturationStatus } from "@/types/enums";
import type {
  AnthropometricRecord,
  MorphologyMetrics,
} from "@/types/anthropometry.types";

function makeMorphology(overrides: Partial<MorphologyMetrics> = {}): MorphologyMetrics {
  return {
    ape_index: 1.013,
    arm_span_height_delta_cm: 2.0,
    posture_screening_flag: false,
    posture_screening_message: null,
    bike_fit_category: "standard",
    bike_fit_guidance:
      "Proporciones estándar. Ajuste de bici según talla y altura del sillín habituales. Re-evaluar cada 3-6 meses.",
    ape_index_advisory: null,
    ...overrides,
  };
}

function makeRecord(
  overrides: Partial<AnthropometricRecord> = {},
): AnthropometricRecord {
  return {
    id: 1,
    athlete_id: 1,
    evaluation_date: "2026-04-14",
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: 157.0,
    sitting_height_cm: 78.0,
    leg_length_cm: 77.0,
    leg_sitting_ratio: 0.987,
    maturity_offset: 0.5,
    age_at_phv: 13.0,
    maturation_status: MaturationStatus.PostPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-04-14T10:00:00",
    notes: null,
    morphology: makeMorphology(),
    ...overrides,
  };
}

describe("MorphologyCard", () => {
  it("muestra estado vacío si no hay registro", () => {
    render(<MorphologyCard />);
    expect(
      screen.getByText(/Registra envergadura en la próxima medición/i),
    ).toBeInTheDocument();
  });

  it("muestra estado vacío si arm_span_cm es null", () => {
    render(
      <MorphologyCard
        latestRecord={makeRecord({ arm_span_cm: null, morphology: null })}
      />,
    );
    expect(
      screen.getByText(/Registra envergadura en la próxima medición/i),
    ).toBeInTheDocument();
  });

  it("renderiza ape index, talla, envergadura y delta", () => {
    render(<MorphologyCard latestRecord={makeRecord()} />);
    expect(screen.getByText(/Ape index/i)).toBeInTheDocument();
    expect(screen.getByText("1.013")).toBeInTheDocument();
    expect(screen.getByText("155.0 cm")).toBeInTheDocument();
    expect(screen.getByText("157.0 cm")).toBeInTheDocument();
    expect(screen.getByText("+2.0 cm")).toBeInTheDocument();
  });

  it("renderiza badge de bike fit estándar", () => {
    render(<MorphologyCard latestRecord={makeRecord()} />);
    expect(screen.getByText("Estándar")).toBeInTheDocument();
    expect(screen.getByText(/Proporciones estándar/i)).toBeInTheDocument();
  });

  it("muestra alerta postural cuando el flag está activo", () => {
    const record = makeRecord({
      morphology: makeMorphology({
        posture_screening_flag: true,
        posture_screening_message:
          "Diferencia talla–envergadura > 3 cm. Recomendar evaluación postural preventiva por médico deportivo.",
        arm_span_height_delta_cm: 4.5,
      }),
    });
    render(<MorphologyCard latestRecord={record} />);
    const alert = screen.getByRole("alert");
    expect(alert).toHaveTextContent(/evaluación postural preventiva/i);
  });

  it("muestra advisory ape index cuando atleta está en Pre/Circa-PHV", () => {
    const record = makeRecord({
      maturation_status: MaturationStatus.CircaPHV,
      morphology: makeMorphology({
        ape_index_advisory:
          "Dato orientativo. En fase de crecimiento activo, la envergadura crece antes que la talla — re-evaluar al completar el brote (Post-PHV).",
      }),
    });
    render(<MorphologyCard latestRecord={record} />);
    expect(
      screen.getByText(/En fase de crecimiento activo/i),
    ).toBeInTheDocument();
  });

  it("renderiza badge bike fit corto cuando ape < 0.97", () => {
    const record = makeRecord({
      morphology: makeMorphology({
        ape_index: 0.95,
        bike_fit_category: "short_reach",
        bike_fit_guidance:
          "Reach corto. Considerar potencia (stem) más corta y manillar con menor barrido. Re-evaluar ajuste cada 3-6 meses.",
      }),
    });
    render(<MorphologyCard latestRecord={record} />);
    expect(screen.getByText("Reach corto")).toBeInTheDocument();
    expect(screen.getByText(/stem.*más corta/i)).toBeInTheDocument();
  });

  it("renderiza badge bike fit largo cuando ape > 1.03", () => {
    const record = makeRecord({
      morphology: makeMorphology({
        ape_index: 1.05,
        bike_fit_category: "long_reach",
        bike_fit_guidance:
          "Reach largo. Considerar potencia (stem) más larga o cuadro con reach mayor. Re-evaluar ajuste cada 3-6 meses.",
      }),
    });
    render(<MorphologyCard latestRecord={record} />);
    expect(screen.getByText("Reach largo")).toBeInTheDocument();
    expect(screen.getByText(/cuadro con reach mayor/i)).toBeInTheDocument();
  });
});
