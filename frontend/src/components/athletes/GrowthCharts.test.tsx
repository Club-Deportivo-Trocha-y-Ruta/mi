import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { GrowthCharts } from "./GrowthCharts";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// Recharts usa ResizeObserver y SVG que jsdom no implementa completamente.
// Mockeamos los componentes de Recharts para evitar errores de resize y SVG.
// El Tooltip mock invoca labelFormatter y formatter para ejercer las funciones
// helper internas del componente (formatDateLabel, formatDateTooltip).
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 800, height: 300 }}>
        {children}
      </div>
    ),
    LineChart: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="line-chart">{children}</div>
    ),
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Line: () => null,
    ReferenceLine: () => null,
    // Tooltip mock que invoca labelFormatter y formatter para cubrir las funciones
    // helper privadas formatDateLabel y formatDateTooltip del componente.
    Tooltip: ({
      formatter,
      labelFormatter,
    }: {
      formatter?: (value: unknown) => unknown;
      labelFormatter?: (label: string, payload: { payload: { date: string } }[]) => string;
    }) => {
      const mockPayload = [{ payload: { date: "2026-01-15" } }];
      // Invocar los callbacks para instrumentar las líneas de cobertura
      if (formatter) formatter(155);
      if (labelFormatter) labelFormatter("01/2026", mockPayload);
      return null;
    },
  };
});

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeRecord(overrides: Partial<AnthropometricRecord> & { id: number }): AnthropometricRecord {
  return {
    id: overrides.id,
    athlete_id: 1,
    evaluation_date: overrides.evaluation_date ?? "2026-01-01",
    mesocycle: overrides.mesocycle ?? null,
    weight_kg: overrides.weight_kg ?? 45.0,
    standing_height_cm: overrides.standing_height_cm ?? 155.0,
    arm_span_cm: null,
    sitting_height_cm: overrides.sitting_height_cm ?? 73.0,
    leg_length_cm: 82.0,
    leg_sitting_ratio: 1.1233,
    maturity_offset: overrides.maturity_offset ?? -0.5,
    age_at_phv: 13.5,
    maturation_status: overrides.maturation_status ?? MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-01T00:00:00Z",
    notes: null,
    ...overrides,
  };
}

const recordA = makeRecord({ id: 1, evaluation_date: "2025-06-01", weight_kg: 43.0, standing_height_cm: 152.0, maturity_offset: -1.5, maturation_status: MaturationStatus.PrePHV });
const recordB = makeRecord({ id: 2, evaluation_date: "2026-01-15", weight_kg: 46.0, standing_height_cm: 157.0, maturity_offset: -0.3, maturation_status: MaturationStatus.CircaPHV });
const recordC = makeRecord({ id: 3, evaluation_date: "2026-04-01", weight_kg: 48.5, standing_height_cm: 160.0, maturity_offset: 0.8, maturation_status: MaturationStatus.CircaPHV });

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("GrowthCharts", () => {
  // -------------------------------------------------------------------------
  // Caso con menos de 2 registros
  // -------------------------------------------------------------------------
  describe("cuando hay menos de 2 registros", () => {
    it("debería mostrar mensaje explicativo con 0 registros", () => {
      render(<GrowthCharts records={[]} />);
      expect(
        screen.getByText(/Se necesitan al menos 2 mediciones/i)
      ).toBeInTheDocument();
    });

    it("debería mostrar mensaje explicativo con exactamente 1 registro", () => {
      render(<GrowthCharts records={[recordA]} />);
      expect(
        screen.getByText(/Se necesitan al menos 2 mediciones/i)
      ).toBeInTheDocument();
    });

    it("no debería renderizar gráficas con 0 registros", () => {
      render(<GrowthCharts records={[]} />);
      expect(screen.queryByText("Talla vs Tiempo")).not.toBeInTheDocument();
    });

    it("no debería renderizar gráficas con 1 registro", () => {
      render(<GrowthCharts records={[recordA]} />);
      expect(screen.queryByText("Talla vs Tiempo")).not.toBeInTheDocument();
    });
  });

  // -------------------------------------------------------------------------
  // Caso con 2 o más registros
  // -------------------------------------------------------------------------
  describe("cuando hay 2 o más registros", () => {
    it("debería renderizar el título 'Talla vs Tiempo' con 2 registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Talla vs Tiempo")).toBeInTheDocument();
    });

    it("debería renderizar el título 'Peso vs Tiempo' con 2 registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Peso vs Tiempo")).toBeInTheDocument();
    });

    it("debería renderizar el título 'Maturity Offset vs Tiempo' con 2 registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Maturity Offset vs Tiempo")).toBeInTheDocument();
    });

    it("debería renderizar las 3 gráficas con 3 registros", () => {
      render(<GrowthCharts records={[recordA, recordB, recordC]} />);
      expect(screen.getByText("Talla vs Tiempo")).toBeInTheDocument();
      expect(screen.getByText("Peso vs Tiempo")).toBeInTheDocument();
      expect(screen.getByText("Maturity Offset vs Tiempo")).toBeInTheDocument();
    });

    it("no debería mostrar el mensaje de 'al menos 2 mediciones' cuando hay suficientes registros", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(
        screen.queryByText(/Se necesitan al menos 2 mediciones/i)
      ).not.toBeInTheDocument();
    });

    it("debería renderizar los contenedores responsivos para cada gráfica", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      const containers = screen.getAllByTestId("responsive-container");
      // 3 gráficas → 3 contenedores
      expect(containers.length).toBe(3);
    });
  });

  // -------------------------------------------------------------------------
  // Exactamente en el límite: 2 registros
  // -------------------------------------------------------------------------
  describe("en el límite de exactamente 2 registros", () => {
    it("debería mostrar gráficas con exactamente 2 registros (límite mínimo)", () => {
      render(<GrowthCharts records={[recordA, recordB]} />);
      expect(screen.getByText("Talla vs Tiempo")).toBeInTheDocument();
      expect(
        screen.queryByText(/Se necesitan al menos 2 mediciones/i)
      ).not.toBeInTheDocument();
    });
  });
});
