/**
 * Tests para PercentileInterpretationBlock.
 *
 * Mockea useGrowthMetrics para aislar el componente del cálculo LMS.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";

import type { GrowthMetrics } from "@/hooks/athletes/useGrowthMetrics";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { MaturationStatus } from "@/types/enums";

import { PercentileInterpretationBlock } from "./PercentileInterpretationBlock";

// ---------------------------------------------------------------------------
// Mock de useGrowthMetrics
// ---------------------------------------------------------------------------

vi.mock("@/hooks/athletes/useGrowthMetrics", () => ({
  useGrowthMetrics: vi.fn(),
}));

import { useGrowthMetrics } from "@/hooks/athletes/useGrowthMetrics";

const mockUseGrowthMetrics = vi.mocked(useGrowthMetrics);

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BIRTH_DATE = "2013-09-01";

const BASE_RECORD: AnthropometricRecord = {
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
};

/** Metrics de retorno para banda "ok" (talla adecuada). */
const METRICS_OK: GrowthMetrics = {
  value: 155.0,
  ageMonths: 148.5,
  zScore: 0.3,
  percentile: 62,
  band: "ok",
  reference: { L: 1, M: 152, S: 0.047 },
};

/** Metrics de retorno para banda "low" (talla baja). */
const METRICS_LOW: GrowthMetrics = {
  value: 128.0,
  ageMonths: 148.5,
  zScore: -2.5,
  percentile: 1,
  band: "low",
  reference: { L: 1, M: 152, S: 0.047 },
};

/** Metrics de retorno para banda "high" (talla muy alta). */
const METRICS_HIGH: GrowthMetrics = {
  value: 178.0,
  ageMonths: 148.5,
  zScore: 2.8,
  percentile: 99,
  band: "high",
  reference: { L: 1, M: 152, S: 0.047 },
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function renderBlock(
  overrides: Partial<Parameters<typeof PercentileInterpretationBlock>[0]> = {},
) {
  return render(
    <PercentileInterpretationBlock
      record={BASE_RECORD}
      sex="M"
      birthDate={BIRTH_DATE}
      indicator="height_for_age"
      {...overrides}
    />,
  );
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("PercentileInterpretationBlock", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // 1. Render con metrics "ok" → muestra label "Adecuada" + frase + valor
  it("con metrics ok muestra label 'Adecuada', frase y valor formateado", () => {
    mockUseGrowthMetrics.mockReturnValue(METRICS_OK);
    renderBlock();

    expect(screen.getByText("Adecuada")).toBeInTheDocument();
    // Frase narrativa de la banda ok para height_for_age
    expect(
      screen.getByText(/La estatura está dentro del rango esperado/i),
    ).toBeInTheDocument();
    // Valor formateado con unidad
    expect(screen.getByText("155.0 cm")).toBeInTheDocument();
  });

  // 2. Render con metrics "low" → muestra label "Talla baja" + frase de alerta
  it("con metrics low muestra label 'Talla baja' y frase de alerta", () => {
    mockUseGrowthMetrics.mockReturnValue(METRICS_LOW);
    renderBlock();

    expect(screen.getByText("Talla baja")).toBeInTheDocument();
    expect(
      screen.getByText(/por debajo del rango esperado/i),
    ).toBeInTheDocument();
    // Muestra el valor de la talla baja
    expect(screen.getByText("128.0 cm")).toBeInTheDocument();
  });

  // 3. Mock retorna null → componente no renderiza nada
  it("cuando useGrowthMetrics retorna null, el componente no renderiza nada", () => {
    mockUseGrowthMetrics.mockReturnValue(null);
    const { container } = renderBlock();

    expect(container.firstChild).toBeNull();
  });

  // 4. Toggle detalles tecnicos → muestra Z-score y percentil
  it("al hacer click en toggle muestra Z-score y percentil exactos", () => {
    mockUseGrowthMetrics.mockReturnValue(METRICS_OK);
    renderBlock();

    // Antes del click no hay detalles
    expect(screen.queryByTestId("technical-details")).not.toBeInTheDocument();

    // Click en toggle
    fireEvent.click(screen.getByRole("button", { name: /Detalles tecnicos/i }));

    // Detalles visibles con Z y percentil
    const details = screen.getByTestId("technical-details");
    expect(details).toBeInTheDocument();
    expect(details.textContent).toMatch(/Z=\+0\.30/);
    expect(details.textContent).toMatch(/P62/);
  });

  // 5. Toggle cierra al hacer click de nuevo
  it("al hacer doble click en toggle, oculta los detalles", () => {
    mockUseGrowthMetrics.mockReturnValue(METRICS_OK);
    renderBlock();

    const btn = screen.getByRole("button", { name: /Detalles tecnicos/i });
    fireEvent.click(btn);
    expect(screen.getByTestId("technical-details")).toBeInTheDocument();

    fireEvent.click(btn);
    expect(screen.queryByTestId("technical-details")).not.toBeInTheDocument();
  });

  // 6. hideAdvanced=true → no muestra boton de detalles
  it("con hideAdvanced=true no muestra el boton de detalles", () => {
    mockUseGrowthMetrics.mockReturnValue(METRICS_OK);
    renderBlock({ hideAdvanced: true });

    expect(screen.queryByRole("button")).not.toBeInTheDocument();
    expect(screen.queryByTestId("technical-details")).not.toBeInTheDocument();
  });

  // 7. Z-score negativo se muestra con signo negativo
  it("Z-score negativo se muestra con signo negativo en detalles", () => {
    mockUseGrowthMetrics.mockReturnValue(METRICS_LOW);
    renderBlock();

    fireEvent.click(screen.getByRole("button", { name: /Detalles tecnicos/i }));

    const details = screen.getByTestId("technical-details");
    expect(details.textContent).toMatch(/Z=-2\.50/);
    expect(details.textContent).toMatch(/P1/);
  });

  // 8. Z-score positivo alto (high) se muestra con signo +
  it("Z-score positivo alto se muestra con signo + en detalles", () => {
    mockUseGrowthMetrics.mockReturnValue(METRICS_HIGH);
    renderBlock();

    fireEvent.click(screen.getByRole("button", { name: /Detalles tecnicos/i }));

    const details = screen.getByTestId("technical-details");
    expect(details.textContent).toMatch(/Z=\+2\.80/);
    expect(details.textContent).toMatch(/P99/);
  });

  // 9. Indicador bmi_for_age formatea el valor con kg/m²
  it("con indicator bmi_for_age muestra el valor con unidad kg/m²", () => {
    const bmiMetrics: GrowthMetrics = {
      ...METRICS_OK,
      value: 18.7,
      band: "ok",
    };
    mockUseGrowthMetrics.mockReturnValue(bmiMetrics);
    renderBlock({ indicator: "bmi_for_age" });

    expect(screen.getByText("18.7 kg/m²")).toBeInTheDocument();
  });

  // 10. Indicador weight_for_age formatea el valor con kg
  it("con indicator weight_for_age muestra el valor con unidad kg", () => {
    const weightMetrics: GrowthMetrics = {
      ...METRICS_OK,
      value: 35.5,
      band: "ok",
    };
    mockUseGrowthMetrics.mockReturnValue(weightMetrics);
    renderBlock({ indicator: "weight_for_age" });

    expect(screen.getByText("35.5 kg")).toBeInTheDocument();
  });
});
