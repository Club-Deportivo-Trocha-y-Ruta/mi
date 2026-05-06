/**
 * Tests para useGrowthMetrics.
 *
 * Valores de referencia calculados con el dataset OMS 2007 Growth Reference
 * (growth-reference-who.json) interpolado a la edad exacta del atleta.
 * Cumple Resolucion MinSalud Colombia 2465/2016.
 *
 * Edad 11 años → birthDate 2015-01-15, evaluation_date 2026-01-15.
 *   - Edad en meses: 132.0
 *   - height_for_age M@132.5: L=1.0, M=143.1126, S=0.04703
 *     → Z(140cm) ≈ -0.43 → percentil ~33 (interpolado a 132.013m)
 *   - bmi_for_age  M@132.5: L=-1.7862, M=16.9392, S=0.1107
 *     → Z(18.0) ≈ 0.53 → percentil ~70
 */

import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";

import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

import { useGrowthMetrics } from "./useGrowthMetrics";
import type { UseGrowthMetricsArgs } from "./useGrowthMetrics";

// ---------------------------------------------------------------------------
// Fixture base
// ---------------------------------------------------------------------------

/** Atleta masculino de 11 años (birthDate 2015-01-15, eval 2026-01-15 = 132 meses). */
const BASE_RECORD: AnthropometricRecord = {
  id: 1,
  athlete_id: 10,
  evaluation_date: "2026-01-15",
  weight_kg: 35.0,
  standing_height_cm: 140.0,
  arm_span_cm: null,
  sitting_height_cm: 68.0,
  leg_length_cm: 72.0,
  leg_sitting_ratio: 1.058,
  maturity_offset: -1.2,
  age_at_phv: 13.5,
  maturation_status: MaturationStatus.PrePHV,
  training_implications: null,
  evaluated_by: 2,
  created_at: "2026-01-15T08:00:00Z",
  notes: null,
  // Sin campos de backend Z por defecto
  height_z_score: null,
  height_percentile: null,
  bmi: null,
  bmi_z_score: null,
  bmi_percentile: null,
  weight_z_score: null,
  weight_percentile: null,
  nutritional_status: null,
};

const BASE_ARGS: UseGrowthMetricsArgs = {
  record: BASE_RECORD,
  sex: "M",
  birthDate: "2015-01-15",
  indicator: "height_for_age",
};

// ---------------------------------------------------------------------------
// Helper: renderHook síncrono (hook puro, no hay async)
// ---------------------------------------------------------------------------

function render(args: UseGrowthMetricsArgs) {
  const { result } = renderHook(() => useGrowthMetrics(args));
  return result.current;
}

// ---------------------------------------------------------------------------
// 1. height_for_age — LMS sin backend Z
// ---------------------------------------------------------------------------

describe("useGrowthMetrics — height_for_age", () => {
  it("calcula Z ≈ -0.43 y percentil ~33 para talla 140cm, M, 11 años", () => {
    const metrics = render(BASE_ARGS);

    expect(metrics).not.toBeNull();
    expect(metrics!.value).toBe(140.0);
    expect(metrics!.ageMonths).toBeCloseTo(132, 0);
    // Z-score esperado por LMS OMS 2007 interpolado a edad exacta (132.013m)
    expect(metrics!.zScore).toBeCloseTo(-0.43, 2);
    // Percentil esperado ≈ 33 (banda ok: -1 ≤ z ≤ 1)
    expect(metrics!.percentile).toBeCloseTo(33, 0);
    expect(metrics!.band).toBe("ok");
    // Referencia interpolada a 132.013m entre rows 131.5 y 132.5 OMS 2007
    expect(metrics!.reference.L).toBeCloseTo(1.0, 2);
    expect(metrics!.reference.M).toBeCloseTo(142.9, 0);
    expect(metrics!.reference.S).toBeCloseTo(0.047, 3);
  });
});

// ---------------------------------------------------------------------------
// 2. bmi_for_age con record.bmi definido (valor backend)
// ---------------------------------------------------------------------------

describe("useGrowthMetrics — bmi_for_age con bmi backend", () => {
  it("usa record.bmi cuando está definido en lugar de calcular desde peso/talla", () => {
    const record: AnthropometricRecord = {
      ...BASE_RECORD,
      // BMI backend definido (18.0)
      bmi: 18.0,
      // peso/talla inconsistentes para verificar que usa bmi, no los calcula
      weight_kg: 999.0,
      standing_height_cm: 999.0,
    };
    const metrics = render({ ...BASE_ARGS, record, indicator: "bmi_for_age" });

    expect(metrics).not.toBeNull();
    // Debe usar el valor backend bmi=18.0
    expect(metrics!.value).toBe(18.0);
    // Z calculado por LMS WHO 2007 para bmi=18.0, M@132.5
    expect(metrics!.zScore).toBeCloseTo(0.53, 2);
    expect(metrics!.percentile).toBeCloseTo(70, 0);
    expect(metrics!.band).toBe("ok");
  });
});

// ---------------------------------------------------------------------------
// 3. bmi_for_age sin record.bmi — calcula desde peso y talla
// ---------------------------------------------------------------------------

describe("useGrowthMetrics — bmi_for_age calculado", () => {
  it("calcula BMI desde peso y talla cuando record.bmi es null", () => {
    const weight_kg = 35.0;
    const standing_height_cm = 143.11; // coincide con la mediana OMS para verificar z ≈ 0
    const record: AnthropometricRecord = {
      ...BASE_RECORD,
      weight_kg,
      standing_height_cm,
      bmi: null,
    };
    const metrics = render({ ...BASE_ARGS, record, indicator: "bmi_for_age" });

    expect(metrics).not.toBeNull();
    // BMI calculado: 35 / (1.4352^2) ≈ 16.99
    const expectedBmi = weight_kg / Math.pow(standing_height_cm / 100, 2);
    expect(metrics!.value).toBeCloseTo(expectedBmi, 2);
    // Banda ok para un z moderado
    expect(["ok", "watch_low"]).toContain(metrics!.band);
  });
});

// ---------------------------------------------------------------------------
// 4. Backend Z-score presente → se usa directamente
// ---------------------------------------------------------------------------

describe("useGrowthMetrics — backend Z-score preferido", () => {
  it("usa height_z_score y height_percentile del record cuando están definidos", () => {
    const record: AnthropometricRecord = {
      ...BASE_RECORD,
      height_z_score: -0.6,
      height_percentile: 27,
    };
    const metrics = render({ ...BASE_ARGS, record, indicator: "height_for_age" });

    expect(metrics).not.toBeNull();
    // Z-score debe ser exactamente el del backend
    expect(metrics!.zScore).toBe(-0.6);
    // Percentil exactamente el del backend
    expect(metrics!.percentile).toBe(27);
    // Banda derivada del z backend
    expect(metrics!.band).toBe("ok"); // -1 ≤ -0.6 ≤ 1
    // value sigue siendo la talla del record
    expect(metrics!.value).toBe(140.0);
  });

  it("no usa height_z_score para el indicador bmi_for_age", () => {
    // Si el record tiene height_z_score pero pedimos bmi_for_age,
    // el hook debe ignorar ese campo y calcular desde LMS.
    const record: AnthropometricRecord = {
      ...BASE_RECORD,
      // BMI real para usar en cálculo
      bmi: 18.0,
      // height_z_score presente pero NO debe usarse para bmi_for_age
      height_z_score: -999.0,
      height_percentile: 1,
      // bmi_z_score ausente
      bmi_z_score: null,
      bmi_percentile: null,
    };
    const metrics = render({ ...BASE_ARGS, record, indicator: "bmi_for_age" });

    expect(metrics).not.toBeNull();
    // Z-score debe ser el calculado por LMS para bmi=18.0, NO -999
    expect(metrics!.zScore).toBeCloseTo(0.53, 2);
    expect(metrics!.zScore).not.toBe(-999.0);
  });
});

// ---------------------------------------------------------------------------
// 5. Record con altura 0 → null
// ---------------------------------------------------------------------------

describe("useGrowthMetrics — valores inválidos", () => {
  it("retorna null cuando standing_height_cm es 0 para height_for_age", () => {
    const record: AnthropometricRecord = {
      ...BASE_RECORD,
      standing_height_cm: 0,
    };
    const metrics = render({ ...BASE_ARGS, record, indicator: "height_for_age" });

    expect(metrics).toBeNull();
  });

  it("retorna null cuando standing_height_cm es 0 para bmi_for_age sin record.bmi", () => {
    const record: AnthropometricRecord = {
      ...BASE_RECORD,
      standing_height_cm: 0,
      bmi: null,
    };
    const metrics = render({ ...BASE_ARGS, record, indicator: "bmi_for_age" });

    expect(metrics).toBeNull();
  });

  it("retorna null para weight_for_age cuando edad > 10 años (OMS no publica >10y)", () => {
    // OMS weight_for_age: 5-10 años (61.5-120.5 meses). 11 años (132m) está fuera.
    const metrics = render({
      ...BASE_ARGS,
      indicator: "weight_for_age",
    });

    expect(metrics).toBeNull();
  });

  it("retorna null cuando la edad está fuera del rango OMS (< 5 años)", () => {
    // birthDate tal que la edad sea ~4 años (48 meses) < mínimo OMS (61.5)
    const metrics = render({
      ...BASE_ARGS,
      birthDate: "2022-01-15", // eval 2026-01-15 → 48 meses
      indicator: "height_for_age",
    });

    expect(metrics).toBeNull();
  });
});

// ---------------------------------------------------------------------------
// 6. Clasificación de bandas por Z-score
// ---------------------------------------------------------------------------

describe("useGrowthMetrics — clasificación de bandas GrowthBand", () => {
  /**
   * Construye args con un height_z_score específico (backend) para verificar
   * la banda sin depender del valor de talla ni del cálculo LMS.
   */
  function makeArgsWithZ(z: number): UseGrowthMetricsArgs {
    return {
      ...BASE_ARGS,
      record: {
        ...BASE_RECORD,
        height_z_score: z,
        height_percentile: null, // sin percentil backend → calculará
      },
      indicator: "height_for_age",
    };
  }

  it("z = -2.1 → banda 'low'", () => {
    const metrics = render(makeArgsWithZ(-2.1));
    expect(metrics!.band).toBe("low");
  });

  it("z = -1.5 → banda 'watch_low'", () => {
    const metrics = render(makeArgsWithZ(-1.5));
    expect(metrics!.band).toBe("watch_low");
  });

  it("z = 0 → banda 'ok'", () => {
    const metrics = render(makeArgsWithZ(0));
    expect(metrics!.band).toBe("ok");
  });

  it("z = +1.5 → banda 'watch_high'", () => {
    const metrics = render(makeArgsWithZ(1.5));
    expect(metrics!.band).toBe("watch_high");
  });

  it("z = +2.1 → banda 'high'", () => {
    const metrics = render(makeArgsWithZ(2.1));
    expect(metrics!.band).toBe("high");
  });

  it("z exacto en límite -2 → banda 'watch_low' (inclusive)", () => {
    const metrics = render(makeArgsWithZ(-2));
    expect(metrics!.band).toBe("watch_low");
  });

  it("z exacto en límite +1 → banda 'ok' (inclusive)", () => {
    const metrics = render(makeArgsWithZ(1));
    expect(metrics!.band).toBe("ok");
  });

  it("z exacto en límite +2 → banda 'watch_high' (inclusive)", () => {
    const metrics = render(makeArgsWithZ(2));
    expect(metrics!.band).toBe("watch_high");
  });
});
