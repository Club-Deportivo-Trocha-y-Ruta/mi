import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TrainingReadiness } from "./TrainingReadiness";
import { MaturationStatus, Sex } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";
import type { GrowthSummary } from "@/types/growth.types";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: 1,
    athlete_id: 1,
    evaluation_date: "2026-01-15",
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

// Atleta 10-12 años con Pre-PHV (sin excepciones — coincide con el plan base del grupo)
const athletePrePHV1012 = makeAthlete({ age_decimal: 11.5 });
const recordPrePHV = makeRecord({ maturation_status: MaturationStatus.PrePHV });

// Atleta 13-15 años con Post-PHV (sin excepciones — coincide con el plan base del grupo)
const athletePostPHV1315 = makeAthlete({ age_decimal: 14.2, birth_date: "2011-09-01" });
const recordPostPHV = makeRecord({ maturation_status: MaturationStatus.PostPHV });

// Atleta con Circa-PHV (reglas más restrictivas que el plan base)
const recordCircaPHV = makeRecord({ maturation_status: MaturationStatus.CircaPHV });

async function expandAllRules() {
  const user = userEvent.setup();
  await user.click(screen.getByRole("button", { name: /ver todas las reglas/i }));
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("TrainingReadiness", () => {
  it("para atleta 10-12 Pre-PHV (sin excepciones): no muestra chips de cambio, solo el aviso de 'sin cambios'", () => {
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
      />,
    );
    expect(
      screen.getByText(/sin cambios respecto al plan base/i),
    ).toBeInTheDocument();
    // El detalle completo ("solo juego libre") solo vive dentro de "Ver todas las reglas"
    expect(screen.queryByText(/solo juego libre/i)).not.toBeInTheDocument();
  });

  it("expande 'Ver todas las reglas' y muestra los nueve criterios, incluido el de 10-12 Pre-PHV", async () => {
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
      />,
    );
    await expandAllRules();
    expect(screen.getByText("Intervalos alta intensidad")).toBeInTheDocument();
    expect(screen.getByText(/solo juego libre/i)).toBeInTheDocument();
    expect(screen.getByText("Fuerza peso externo")).toBeInTheDocument();
    expect(screen.getByText("Test FC máxima")).toBeInTheDocument();
  });

  it("para atleta 13-15 Post-PHV (sin excepciones): no muestra chips de cambio", () => {
    render(
      <TrainingReadiness
        athlete={athletePostPHV1315}
        latestRecord={recordPostPHV}
      />,
    );
    expect(
      screen.getByText(/sin cambios respecto al plan base/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/Max 2 sesiones\/semana/i)).not.toBeInTheDocument();
  });

  it("expande 'Ver todas las reglas' para 13-15 Post-PHV y ve alta intensidad con precaución", async () => {
    render(
      <TrainingReadiness
        athlete={athletePostPHV1315}
        latestRecord={recordPostPHV}
      />,
    );
    await expandAllRules();
    expect(screen.getByText("Intervalos alta intensidad")).toBeInTheDocument();
    expect(screen.getByText(/Max 2 sesiones\/semana/i)).toBeInTheDocument();
  });

  it("para atleta con Circa-PHV: las reglas que difieren del plan base aparecen como chips sin expandir nada", () => {
    const athleteCircaPHV1315 = makeAthlete({ age_decimal: 13.8 });
    render(
      <TrainingReadiness
        athlete={athleteCircaPHV1315}
        latestRecord={recordCircaPHV}
      />,
    );
    // "Sin cambios" no debe aparecer: sí hay excepciones en Circa-PHV
    expect(
      screen.queryByText(/sin cambios respecto al plan base/i),
    ).not.toBeInTheDocument();
    // Al menos una regla muestra el texto específico de Circa-PHV, visible sin expandir
    const forbidden = screen.getAllByText(/Prohibido en Circa-PHV/);
    expect(forbidden.length).toBeGreaterThanOrEqual(1);
    // Las etiquetas de estado usan el vocabulario del contrato (icono + texto, nunca solo color)
    expect(screen.getAllByText("No permitido").length).toBeGreaterThanOrEqual(1);
  });

  it("muestra alerta de vulnerabilidad ósea cuando maturation_status es Circa-PHV (sin prop alerts)", () => {
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

  it("sin latestRecord renderiza sin error", () => {
    expect(() =>
      render(
        <TrainingReadiness
          athlete={makeAthlete({ age_decimal: 12.0 })}
        />,
      ),
    ).not.toThrow();
    expect(screen.getByText("Qué cambia en el entrenamiento")).toBeInTheDocument();
  });

  it("no muestra el nombre del atleta como chip (retirado en el rediseño)", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ first_name: "Juan", last_name: "García" })}
        latestRecord={recordPrePHV}
      />,
    );
    expect(screen.queryByText("Juan García")).not.toBeInTheDocument();
  });

  it("para edad fuera del modelo (16 años) muestra mensaje de rango", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ age_decimal: 16.0 })}
        latestRecord={recordPostPHV}
      />,
    );
    expect(screen.getByText(/Rango de edad fuera del modelo/i)).toBeInTheDocument();
  });

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

  it("muestra alerta de 'Talla muy baja' cuando height_percentile < 3 (sin prop alerts)", () => {
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

  it("G-04: ninguna estimación numérica de FC máxima (lpm) aparece, ni colapsada ni expandida", async () => {
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
      />,
    );
    expect(screen.queryByText(/lpm/i)).not.toBeInTheDocument();
    await expandAllRules();
    expect(screen.getByText("Test FC máxima")).toBeInTheDocument();
    expect(screen.getByText(/Sin test de FC máxima/i)).toBeInTheDocument();
    expect(screen.queryByText(/lpm/i)).not.toBeInTheDocument();
  });

  it("para atleta Circa-PHV no muestra ninguna estimación numérica de FC máxima (lpm)", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ age_decimal: 13.8 })}
        latestRecord={recordCircaPHV}
      />,
    );
    expect(screen.queryByText(/lpm/i)).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------
  // Prop `alerts` (GrowthSummary["alerts"]) — reemplaza el cálculo local
  // ---------------------------------------------------------------------

  it("usa la prop `alerts` en lugar del cálculo local cuando está presente", () => {
    const summaryAlerts: GrowthSummary["alerts"] = ["circa_phv"];
    // latestRecord es Pre-PHV (no dispararía la alerta local), pero la prop sí la trae
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
        alerts={summaryAlerts}
      />,
    );
    expect(
      screen.getByText(/máxima vulnerabilidad ósea/i),
    ).toBeInTheDocument();
  });

  it("con `alerts` presente pero sin códigos relevantes, no muestra alertas aunque el registro sea Circa-PHV", () => {
    const summaryAlerts: GrowthSummary["alerts"] = ["rapid_growth"];
    render(
      <TrainingReadiness
        athlete={makeAthlete({ age_decimal: 13.8 })}
        latestRecord={recordCircaPHV}
        alerts={summaryAlerts}
      />,
    );
    // La prop manda: como no trae "circa_phv", no se muestra el aviso óseo
    expect(
      screen.queryByText(/máxima vulnerabilidad ósea/i),
    ).not.toBeInTheDocument();
  });

  it("mapea `height_p3` y `bmi_p3` de la prop `alerts` a sus mensajes", () => {
    const summaryAlerts: GrowthSummary["alerts"] = ["height_p3", "bmi_p3"];
    render(
      <TrainingReadiness
        athlete={athletePrePHV1012}
        latestRecord={recordPrePHV}
        alerts={summaryAlerts}
      />,
    );
    expect(screen.getByText(/Talla muy baja/i)).toBeInTheDocument();
    expect(screen.getByText(/Delgadez severa/i)).toBeInTheDocument();
  });

  it("con `alerts` como arreglo vacío no muestra ninguna alerta", () => {
    render(
      <TrainingReadiness
        athlete={makeAthlete({ age_decimal: 13.8 })}
        latestRecord={recordCircaPHV}
        alerts={[]}
      />,
    );
    expect(
      screen.queryByText(/máxima vulnerabilidad ósea/i),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/Talla muy baja/i)).not.toBeInTheDocument();
  });
});
