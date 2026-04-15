import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { TrainingReadiness } from "./TrainingReadiness";
import { MaturationStatus, Sex } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: 1,
    athlete_id: 1,
    evaluation_date: "2026-01-15",
    mesocycle: null,
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 77.0,
    leg_sitting_ratio: 0.987,
    maturity_offset: -0.3,
    age_at_phv: 13.2,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-15T10:00:00",
    notes: null,
    height_z_score: 0.3,
    height_percentile: 62,
    bmi: 18.7,
    bmi_z_score: -0.2,
    bmi_percentile: 42,
    weight_z_score: 0.1,
    weight_percentile: 54,
    nutritional_status: "adecuado",
    ...overrides,
  };
}

function makeAthlete(overrides: Partial<AthleteDetailOut> = {}): AthleteDetailOut {
  return {
    id: 1,
    user_id: 1,
    first_name: "Atleta",
    last_name: "Prueba",
    birth_date: "2013-09-01",
    sex: Sex.M,
    club_join_date: "2024-01-01",
    years_in_club: 2,
    age_decimal: 12.3,
    category: "Pre-juvenil",
    club_id: 1,
    created_at: "2024-01-01",
    latest_anthropometry: null,
    ...overrides,
  };
}

// Atleta 10-12 años con Pre-PHV
const athletePrePHV1012 = makeAthlete({ age_decimal: 11.5 });
const recordPrePHV = makeRecord({ maturation_status: MaturationStatus.PrePHV });

// Atleta 13-15 años con Post-PHV
const athletePostPHV1315 = makeAthlete({ age_decimal: 14.2, birth_date: "2011-09-01" });
const recordPostPHV = makeRecord({ maturation_status: MaturationStatus.PostPHV });

// Atleta con Circa-PHV
const recordCircaPHV = makeRecord({ maturation_status: MaturationStatus.CircaPHV });

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingReadiness", () => {
  // 1. Atleta 10-12 años Pre-PHV: "Intervalos alta intensidad" aparece como prohibido (✗)
  it("para atleta 10-12 Pre-PHV: 'Intervalos alta intensidad' está prohibido", () => {
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
      />,
    );
    expect(screen.getByText("Intervalos alta intensidad")).toBeInTheDocument();
    // El texto de detalle explica el motivo de la prohibición para este grupo de edad
    expect(screen.getByText(/solo juego libre/i)).toBeInTheDocument();
  });

  // 2. Atleta 13-15 años Post-PHV: "Intervalos alta intensidad" aparece como "caution" (Max 2 sesiones)
  it("para atleta 13-15 Post-PHV: 'Intervalos alta intensidad' permitido con precaución", () => {
    render(
      <TrainingReadiness
        athlete={athletePostPHV1315}
        latestRecord={recordPostPHV}
      />,
    );
    expect(screen.getByText("Intervalos alta intensidad")).toBeInTheDocument();
    expect(screen.getByText(/Max 2 sesiones\/semana/i)).toBeInTheDocument();
  });

  // 3. Atleta Circa-PHV: reglas más restrictivas que el grupo de edad
  //    Intervalos alta intensidad prohibidos (superando incluso las reglas de 13-15)
  it("para atleta con Circa-PHV: aplica reglas más restrictivas (intervalos prohibidos)", () => {
    const athleteCircaPHV1315 = makeAthlete({ age_decimal: 13.8 });
    render(
      <TrainingReadiness
        athlete={athleteCircaPHV1315}
        latestRecord={recordCircaPHV}
      />,
    );
    // En Circa-PHV varios elementos muestran "Prohibido en Circa-PHV".
    // Verificamos que hay al menos uno (la regla de intervalos es la más importante).
    const forbidden = screen.getAllByText(/Prohibido en Circa-PHV/);
    expect(forbidden.length).toBeGreaterThanOrEqual(1);
  });

  // 4. Alerta de Circa-PHV visible cuando maturation_status === 'Circa-PHV'
  it("muestra alerta de vulnerabilidad ósea cuando maturation_status es Circa-PHV", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ age_decimal: 12.5 })}
        latestRecord={recordCircaPHV}
      />,
    );
    expect(
      screen.getByText(/máxima vulnerabilidad ósea/i),
    ).toBeInTheDocument();
  });

  // 5. Sin latestRecord: renderiza sin error
  it("sin latestRecord renderiza sin error", () => {
    expect(() =>
      render(
        <TrainingReadiness
          athlete={makeAthlete({ age_decimal: 12.0 })}
        />,
      ),
    ).not.toThrow();
    expect(screen.getByText("Recomendaciones de entrenamiento")).toBeInTheDocument();
  });

  // 6. El header siempre muestra el nombre del atleta
  it("muestra el nombre del atleta en el header", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ first_name: "Juan", last_name: "García" })}
        latestRecord={recordPrePHV}
      />,
    );
    expect(screen.getByText("Juan García")).toBeInTheDocument();
  });

  // 7. Para edad fuera del modelo (>15 o <10) muestra mensaje de rango
  it("para edad fuera del modelo (16 años) muestra mensaje de rango", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ age_decimal: 16.0 })}
        latestRecord={recordPostPHV}
      />,
    );
    expect(screen.getByText(/Rango de edad fuera del modelo/i)).toBeInTheDocument();
  });

  // 8. Atleta Pre-PHV NO tiene alerta de vulnerabilidad ósea
  it("atleta Pre-PHV no muestra alerta de vulnerabilidad ósea", () => {
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
      />,
    );
    expect(
      screen.queryByText(/máxima vulnerabilidad ósea/i),
    ).not.toBeInTheDocument();
  });

  // 9. Fuerza peso externo prohibida para 10-12 años Pre-PHV
  it("para 10-12 Pre-PHV: 'Fuerza peso externo' está prohibida", () => {
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
      />,
    );
    expect(screen.getByText("Fuerza peso externo")).toBeInTheDocument();
    // Puede haber múltiples textos con "Prohibido en 10-12" (intervalos y fuerza externa)
    const matches = screen.getAllByText(/Prohibido en 10-12/i);
    expect(matches.length).toBeGreaterThanOrEqual(1);
  });

  // 10. Alerta de talla muy baja (height_percentile < 3)
  it("muestra alerta de 'Talla muy baja' cuando height_percentile < 3", () => {
    const recordTallaBaja = makeRecord({
      maturation_status: MaturationStatus.PrePHV,
      height_percentile: 1,
    });
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordTallaBaja}
      />,
    );
    expect(screen.getByText(/Talla muy baja/i)).toBeInTheDocument();
  });

  // 11. La nota al pie menciona LTAD y edad biológica
  it("muestra nota al pie sobre LTAD y edad biológica", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ age_decimal: 12.0 })}
        latestRecord={recordPrePHV}
      />,
    );
    expect(screen.getByText(/LTAD/)).toBeInTheDocument();
    expect(screen.getByText(/edad biológica/i)).toBeInTheDocument();
  });
});
