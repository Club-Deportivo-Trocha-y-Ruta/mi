/**
 * Tests — PercentileTable (feature 040, T047/US3).
 *
 * Alternativa visible (WCAG) a `PercentileChart` cuando `view="table"` —
 * per `contracts/growth-tab-ui.md`: tabla shadcn con mes-año, edad, valor,
 * Z, percentil y una insignia de banda, una fila por registro, usando
 * `useGrowthMetrics` (no recalcula LMS por su cuenta). El estado vacío
 * ("Sin mediciones") viene de la fila "Table" en la tabla de estados del
 * contrato.
 *
 * Se mockea `useGrowthMetrics` para controlar valor/Z/percentil/banda por
 * registro sin depender del JSON OMS real (mismo patrón que
 * `PercentileInterpretationBlock.test.tsx`).
 *
 * Datos: sintéticos, sin nombres ni fechas de nacimiento reales de menores.
 */
import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";

import { PercentileTable } from "@/components/athletes/growth/PercentileTable";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

vi.mock("@/hooks/athletes/useGrowthMetrics", () => ({
  useGrowthMetrics: vi.fn(),
}));

import { useGrowthMetrics } from "@/hooks/athletes/useGrowthMetrics";
import type { GrowthMetrics } from "@/hooks/athletes/useGrowthMetrics";

const mockUseGrowthMetrics = vi.mocked(useGrowthMetrics);

// ---------------------------------------------------------------------------
// Fixtures — sintéticas, sin datos reales de deportistas menores de edad.
// ---------------------------------------------------------------------------

const BASE_BIRTH_DATE = "2013-09-01";

function makeRecord(
  overrides: Partial<AnthropometricRecord> & { id: number },
): AnthropometricRecord {
  return {
    athlete_id: 1,
    evaluation_date: "2026-01-23",
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
    created_at: "2026-01-23T10:00:00",
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

function makeMetrics(overrides: Partial<GrowthMetrics> = {}): GrowthMetrics {
  return {
    value: 155.0,
    ageMonths: 150,
    zScore: 0.3,
    percentile: 62,
    band: "talla_adecuada",
    reference: { L: 1, M: 142.9, S: 0.047 },
    source: "stored",
    ...overrides,
  };
}

beforeEach(() => {
  mockUseGrowthMetrics.mockReset();
  mockUseGrowthMetrics.mockReturnValue(makeMetrics());
});

// ---------------------------------------------------------------------------
// 1. Encabezados y estructura
// ---------------------------------------------------------------------------

describe("PercentileTable — encabezados", () => {
  it("expone columnas mes-año, edad, valor, Z, percentil y banda", () => {
    render(
      <PercentileTable
        records={[makeRecord({ id: 1 })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    const table = screen.getByRole("table");
    const headerText = within(table)
      .getAllByRole("columnheader")
      .map((h) => h.textContent ?? "")
      .join(" ")
      .toLowerCase();

    expect(headerText).toMatch(/mes|fecha/);
    expect(headerText).toMatch(/edad/);
    expect(headerText).toMatch(/valor/);
    expect(headerText).toMatch(/z/);
    expect(headerText).toMatch(/percentil/);
    expect(headerText).toMatch(/banda/);
  });
});

// ---------------------------------------------------------------------------
// 2. Filas = registros
// ---------------------------------------------------------------------------

describe("PercentileTable — filas por registro", () => {
  it("renderiza una fila de datos por cada registro recibido", () => {
    render(
      <PercentileTable
        records={[
          makeRecord({ id: 1, evaluation_date: "2025-06-01" }),
          makeRecord({ id: 2, evaluation_date: "2025-09-01" }),
          makeRecord({ id: 3, evaluation_date: "2026-01-23" }),
        ]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    const table = screen.getByRole("table");
    const rows = within(table).getAllByRole("row");
    // 1 fila de encabezado + 3 filas de datos.
    expect(rows).toHaveLength(4);
  });

  it("con 0 registros muestra el estado vacío 'Sin mediciones' y no dibuja filas de datos", () => {
    render(
      <PercentileTable
        records={[]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    expect(screen.getByText(/sin mediciones/i)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 3. Valores por columna — vienen de useGrowthMetrics, no recalculados aquí
// ---------------------------------------------------------------------------

describe("PercentileTable — valores mostrados", () => {
  it("muestra valor, Z-score y percentil devueltos por useGrowthMetrics", () => {
    mockUseGrowthMetrics.mockReturnValue(
      makeMetrics({ value: 158.4, zScore: 1.23, percentile: 89 }),
    );

    render(
      <PercentileTable
        records={[makeRecord({ id: 1 })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    const table = screen.getByRole("table");
    const dataRow = within(table).getAllByRole("row")[1];
    expect(dataRow).toHaveTextContent("158.4");
    expect(dataRow).toHaveTextContent("1.23");
    expect(dataRow).toHaveTextContent("89");
  });

  it("la insignia de banda muestra una etiqueta legible, no la clave cruda del enum", () => {
    mockUseGrowthMetrics.mockReturnValue(makeMetrics({ band: "talla_adecuada" }));

    render(
      <PercentileTable
        records={[makeRecord({ id: 1 })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    const table = screen.getByRole("table");
    expect(within(table).queryByText("talla_adecuada")).not.toBeInTheDocument();
    // Vocabulario de bands.ts: talla_adecuada -> coachLabel "Adecuada".
    expect(within(table).getByText(/adecuad/i)).toBeInTheDocument();
  });

  it("distintas bandas por fila producen etiquetas distintas (color nunca es el único canal)", () => {
    mockUseGrowthMetrics.mockImplementation(({ record }) =>
      record.id === 1
        ? makeMetrics({ band: "retraso_talla" })
        : makeMetrics({ band: "talla_alta" }),
    );

    render(
      <PercentileTable
        records={[
          makeRecord({ id: 1, evaluation_date: "2025-06-01" }),
          makeRecord({ id: 2, evaluation_date: "2026-01-23" }),
        ]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    const table = screen.getByRole("table");
    expect(within(table).getByText(/talla baja/i)).toBeInTheDocument();
    expect(within(table).getByText(/talla alta/i)).toBeInTheDocument();
  });

  it("no expone el día exacto de la evaluación en la columna de fecha (privacidad)", () => {
    // Día 23 elegido para no colisionar con ningún otro número mostrado en la fila
    // (edad en años con un decimal, valor con un decimal, Z con dos decimales).
    render(
      <PercentileTable
        records={[makeRecord({ id: 1, evaluation_date: "2026-01-23" })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    const table = screen.getByRole("table");
    const dataRow = within(table).getAllByRole("row")[1];
    const dateCell = within(dataRow).getAllByRole("cell")[0];
    expect(dateCell.textContent).not.toMatch(/23/);
    expect(dateCell.textContent).toMatch(/2026/);
  });
});

// ---------------------------------------------------------------------------
// 4. preset="family" — alternativa accesible para la familia (FR-016)
//
// `docs/18-growth-module-redesign/proposal.md` §5.2 exige que la vista de
// tabla siga disponible en modo padre ("table view available"), pero FR-016
// prohíbe mostrarle Z-scores, percentiles y las etiquetas clínicas del coach.
// ---------------------------------------------------------------------------

describe("PercentileTable — preset family", () => {
  it("no expone las columnas Z ni Percentil", () => {
    render(
      <PercentileTable
        records={[makeRecord({ id: 1 })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        preset="family"
      />,
    );

    const table = screen.getByRole("table");
    const headers = within(table)
      .getAllByRole("columnheader")
      .map((h) => (h.textContent ?? "").trim().toLowerCase());

    expect(headers).not.toContain("z");
    expect(headers).not.toContain("percentil");
    expect(headers).toContain("estado");
    // Las columnas que sí sobreviven (mes-año, edad, valor) siguen presentes.
    expect(headers).toContain("mes");
    expect(headers).toContain("edad");
    expect(headers).toContain("valor");
  });

  it("no imprime el Z-score ni el percentil en ninguna celda", () => {
    render(
      <PercentileTable
        records={[makeRecord({ id: 1 })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        preset="family"
      />,
    );

    const table = screen.getByRole("table");
    // +0.30 (Z formateado) y P62 (percentil) son los valores del mock.
    expect(table.textContent).not.toMatch(/\+0\.30/);
    expect(table.textContent).not.toMatch(/\bP62\b/);
  });

  it("usa la etiqueta familiar de la banda, nunca la clínica del coach", () => {
    render(
      <PercentileTable
        records={[makeRecord({ id: 1 })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        preset="family"
      />,
    );

    const table = screen.getByRole("table");
    expect(within(table).getByText("Dentro del rango esperado")).toBeInTheDocument();
    expect(within(table).queryByText("Adecuada")).not.toBeInTheDocument();
  });

  it("por defecto (sin preset) sigue siendo la tabla de coach con Z y percentil", () => {
    render(
      <PercentileTable
        records={[makeRecord({ id: 1 })]}
        indicator="height_for_age"
        sex="M"
        birthDate={BASE_BIRTH_DATE}
      />,
    );

    const table = screen.getByRole("table");
    expect(table.textContent).toMatch(/\+0\.30/);
    expect(table.textContent).toMatch(/P62/);
    expect(within(table).getByText("Adecuada")).toBeInTheDocument();
  });
});
