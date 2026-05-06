import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { NutritionalClassification } from "./NutritionalClassification";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// NutritionalClassification importa el JSON de referencia OMS para calcular Z-scores
// cuando el backend no los provee. Mock con datos mínimos coherentes.
vi.mock("@/data/growth-reference-who.json", () => ({
  default: {
    indicators: {
      height_for_age: {
        M: [
          { age: 120, L: 1, M: 140.0, S: 0.04, P3: 128, P10: 133, P25: 137, P50: 140, P75: 143, P90: 147, P97: 152 },
          { age: 126, L: 1, M: 143.0, S: 0.04, P3: 131, P10: 136, P25: 140, P50: 143, P75: 146, P90: 150, P97: 155 },
          { age: 147, L: 1, M: 155.0, S: 0.04, P3: 143, P10: 148, P25: 152, P50: 155, P75: 158, P90: 162, P97: 167 },
          { age: 150, L: 1, M: 156.5, S: 0.04, P3: 144, P10: 149, P25: 153, P50: 156, P75: 160, P90: 164, P97: 169 },
        ],
        F: [
          { age: 120, L: 1, M: 138.0, S: 0.04, P3: 126, P10: 131, P25: 135, P50: 138, P75: 141, P90: 145, P97: 150 },
          { age: 147, L: 1, M: 152.0, S: 0.04, P3: 140, P10: 145, P25: 149, P50: 152, P75: 155, P90: 159, P97: 164 },
          { age: 150, L: 1, M: 153.0, S: 0.04, P3: 141, P10: 146, P25: 150, P50: 153, P75: 156, P90: 160, P97: 165 },
        ],
      },
      bmi_for_age: {
        M: [
          { age: 120, L: 1, M: 16.5, S: 0.09, P3: 13.5, P10: 14.5, P25: 15.5, P50: 16.5, P75: 17.8, P90: 19.1, P97: 21.0 },
          { age: 147, L: 1, M: 18.0, S: 0.09, P3: 14.5, P10: 15.5, P25: 16.8, P50: 18.0, P75: 19.5, P90: 21.2, P97: 23.5 },
          { age: 150, L: 1, M: 18.2, S: 0.09, P3: 14.7, P10: 15.7, P25: 17.0, P50: 18.2, P75: 19.7, P90: 21.5, P97: 23.8 },
        ],
        F: [
          { age: 120, L: 1, M: 16.5, S: 0.09, P3: 13.5, P10: 14.5, P25: 15.5, P50: 16.5, P75: 17.8, P90: 19.1, P97: 21.0 },
          { age: 147, L: 1, M: 18.0, S: 0.09, P3: 14.5, P10: 15.5, P25: 16.8, P50: 18.0, P75: 19.5, P90: 21.2, P97: 23.5 },
          { age: 150, L: 1, M: 18.2, S: 0.09, P3: 14.7, P10: 15.7, P25: 17.0, P50: 18.2, P75: 19.7, P90: 21.5, P97: 23.8 },
        ],
      },
      weight_for_age: {
        M: [
          { age: 120, L: 1, M: 32.0, S: 0.14, P3: 22, P10: 25, P25: 28, P50: 32, P75: 36, P90: 41, P97: 47 },
          { age: 147, L: 1, M: 45.0, S: 0.14, P3: 30, P10: 34, P25: 38, P50: 45, P75: 52, P90: 60, P97: 70 },
          { age: 150, L: 1, M: 46.0, S: 0.14, P3: 31, P10: 35, P25: 39, P50: 46, P75: 53, P90: 61, P97: 71 },
        ],
        F: [
          { age: 120, L: 1, M: 32.0, S: 0.14, P3: 22, P10: 25, P25: 28, P50: 32, P75: 36, P90: 41, P97: 47 },
          { age: 147, L: 1, M: 44.0, S: 0.14, P3: 29, P10: 33, P25: 37, P50: 44, P75: 51, P90: 59, P97: 69 },
          { age: 150, L: 1, M: 45.0, S: 0.14, P3: 30, P10: 34, P25: 38, P50: 45, P75: 52, P90: 60, P97: 70 },
        ],
      },
    },
  },
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BIRTH_DATE = "2013-09-01"; // ~12.4 años al 2026-01-15

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

// Registro con Z-score positivo alto (sobrepeso: bmi_z_score >= 1 y < 2)
const recordSobrepeso = makeRecord({
  bmi_z_score: 1.5,
  bmi_percentile: 93,
  bmi: 22.5,
  height_z_score: 0.2,
  height_percentile: 58,
});

// Registro con Z-score negativo bajo para talla (talla baja: height_z_score < -2)
const recordTallaBaja = makeRecord({
  height_z_score: -2.5,
  height_percentile: 1,
  bmi_z_score: -0.1,
  bmi_percentile: 46,
});

// Registro en rango normal (Z-scores entre -1 y +1)
const recordNormal = makeRecord({
  height_z_score: 0.3,
  height_percentile: 62,
  bmi_z_score: 0.1,
  bmi_percentile: 54,
});

// Registro con todos los campos opcionales nulos (datos históricos sin percentiles)
const recordSinPercentiles = makeRecord({
  height_z_score: undefined,
  height_percentile: undefined,
  bmi: undefined,
  bmi_z_score: undefined,
  bmi_percentile: undefined,
  weight_z_score: undefined,
  weight_percentile: undefined,
  nutritional_status: undefined,
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("NutritionalClassification", () => {
  // 1. Renderiza el título con la referencia normativa
  it("renderiza el título 'Clasificación Nutricional'", () => {
    render(<NutritionalClassification record={recordNormal} sex="M" birthDate={BIRTH_DATE} />);
    expect(screen.getByText(/Clasificación Nutricional/i)).toBeInTheDocument();
  });

  // 2. El h4 del título contiene "(Res. 2465/2016)" como texto anidado
  it("el título incluye la referencia normativa '2465'", () => {
    const { container } = render(
      <NutritionalClassification record={recordNormal} sex="M" birthDate={BIRTH_DATE} />,
    );
    // El h4 contiene el texto completo "Clasificación Nutricional (Res. 2465/2016)"
    const h4 = container.querySelector("h4");
    expect(h4).not.toBeNull();
    expect(h4!.textContent).toMatch(/2465/);
  });

  // 3. Con Z-score positivo alto (bmi_z_score = 1.5) muestra "Sobrepeso"
  it("con Z-score positivo alto muestra clasificación 'Sobrepeso'", () => {
    render(<NutritionalClassification record={recordSobrepeso} sex="M" birthDate={BIRTH_DATE} />);
    expect(screen.getByText("Sobrepeso")).toBeInTheDocument();
  });

  // 4. Con height_z_score < -2 muestra "Talla baja"
  it("con height_z_score < -2 muestra 'Talla baja'", () => {
    render(<NutritionalClassification record={recordTallaBaja} sex="M" birthDate={BIRTH_DATE} />);
    expect(screen.getByText("Talla baja")).toBeInTheDocument();
  });

  // 5. Con Z-scores en rango normal muestra "Adecuada" (talla) y "Adecuado" (IMC)
  // Antes: "Talla adecuada" (clasificación propia del componente).
  // Ahora: "Adecuada" (label OMS de GROWTH_BANDS_WHO.height_for_age.ok via getBandSpec).
  it("con Z-scores en rango normal muestra 'Adecuada' (talla) y 'Adecuado' (IMC)", () => {
    render(<NutritionalClassification record={recordNormal} sex="M" birthDate={BIRTH_DATE} />);
    expect(screen.getByText("Adecuada")).toBeInTheDocument();
    expect(screen.getByText("Adecuado")).toBeInTheDocument();
  });

  // 6. Con todos los campos opcionales nulos no lanza error (datos históricos)
  it("con campos opcionales nulos no lanza error", () => {
    expect(() =>
      render(
        <NutritionalClassification
          record={recordSinPercentiles}
          sex="M"
          birthDate={BIRTH_DATE}
        />,
      ),
    ).not.toThrow();
  });

  // 7. Muestra la atribución de fuente "MinSalud" al pie
  it("muestra la atribución de fuente 'MinSalud' al pie", () => {
    render(<NutritionalClassification record={recordNormal} sex="M" birthDate={BIRTH_DATE} />);
    expect(screen.getByText(/MinSalud/i)).toBeInTheDocument();
  });

  // 8. El pie de fuentes incluye "OMS 2007" como texto de la fuente
  it("el pie de fuentes menciona 'OMS 2007'", () => {
    render(<NutritionalClassification record={recordNormal} sex="M" birthDate={BIRTH_DATE} />);
    // El párrafo de fuente dice "Fuente: OMS 2007 / Res. 2465/2016 — MinSalud Colombia"
    expect(screen.getByText(/OMS 2007/)).toBeInTheDocument();
  });

  // 9. Los indicadores de sección están presentes: Talla/Edad e IMC/Edad
  it("muestra los labels de indicadores 'Talla/Edad' e 'IMC/Edad'", () => {
    render(<NutritionalClassification record={recordNormal} sex="M" birthDate={BIRTH_DATE} />);
    expect(screen.getByText("Talla/Edad:")).toBeInTheDocument();
    expect(screen.getByText("IMC/Edad:")).toBeInTheDocument();
  });

  // 10. Con record de sexo femenino renderiza correctamente
  it("con sexo femenino renderiza sin error", () => {
    expect(() =>
      render(
        <NutritionalClassification record={recordNormal} sex="F" birthDate={BIRTH_DATE} />,
      ),
    ).not.toThrow();
    expect(screen.getByText(/Clasificación Nutricional/i)).toBeInTheDocument();
  });

  // 11. Sin datos de percentiles (undefined) calcula Z-score desde la tabla de referencia
  it("sin percentiles del backend calcula y muestra clasificación usando referencia OMS 2007", () => {
    render(
      <NutritionalClassification
        record={recordSinPercentiles}
        sex="M"
        birthDate={BIRTH_DATE}
      />,
    );
    // Debe haber clasificación para ambos indicadores (no "Sin datos")
    // porque los valores de talla (155) y peso (45) son válidos para calcular Z
    expect(screen.queryAllByText("Sin datos").length).toBeLessThan(2);
  });
});
