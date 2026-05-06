import { describe, it, expect, vi } from "vitest";
import { render } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { PercentileCurves } from "./PercentileCurves";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — idénticos a PercentileCurves.test.tsx para consistencia
// ---------------------------------------------------------------------------

vi.mock("@/hooks/athletes/useGrowthMetrics", () => ({
  useGrowthMetrics: () => ({
    value: 155.0,
    ageMonths: 148,
    zScore: 0.3,
    percentile: 62,
    band: "ok",
    reference: { L: 1, M: 142.9, S: 0.047 },
  }),
}));

// Recharts no genera SVG real en jsdom — el mock evita errores SVG y
// falsos positivos de axe sobre atributos SVG no estándar en jsdom.
vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 800, height: 480 }}>
        {children}
      </div>
    ),
    ComposedChart: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="composed-chart">{children}</div>
    ),
    CartesianGrid: () => null,
    XAxis: () => null,
    YAxis: () => null,
    Area: () => null,
    Line: () => null,
    ReferenceLine: () => null,
    Tooltip: () => null,
    Legend: () => null,
  };
});

vi.mock("@/data/growth-reference-who.json", () => ({
  default: {
    indicators: {
      height_for_age: {
        M: [
          { age: 120, L: 1, M: 140.0, S: 0.04, P3: 128, P10: 133, P25: 137, P50: 140, P75: 143, P90: 147, P97: 152 },
          { age: 126, L: 1, M: 143.0, S: 0.04, P3: 131, P10: 136, P25: 140, P50: 143, P75: 146, P90: 150, P97: 155 },
          { age: 132, L: 1, M: 148.0, S: 0.04, P3: 136, P10: 141, P25: 145, P50: 148, P75: 151, P90: 155, P97: 160 },
        ],
        F: [
          { age: 120, L: 1, M: 138.0, S: 0.04, P3: 126, P10: 131, P25: 135, P50: 138, P75: 141, P90: 145, P97: 150 },
          { age: 126, L: 1, M: 142.0, S: 0.04, P3: 130, P10: 135, P25: 139, P50: 142, P75: 145, P90: 149, P97: 154 },
        ],
      },
      bmi_for_age: {
        M: [
          { age: 120, L: 1, M: 16.5, S: 0.09, P3: 13.5, P10: 14.5, P25: 15.5, P50: 16.5, P75: 17.8, P90: 19.1, P97: 21.0 },
          { age: 126, L: 1, M: 16.8, S: 0.09, P3: 13.8, P10: 14.8, P25: 15.8, P50: 16.8, P75: 18.1, P90: 19.5, P97: 21.5 },
        ],
        F: [
          { age: 120, L: 1, M: 16.5, S: 0.09, P3: 13.5, P10: 14.5, P25: 15.5, P50: 16.5, P75: 17.8, P90: 19.1, P97: 21.0 },
          { age: 126, L: 1, M: 16.8, S: 0.09, P3: 13.8, P10: 14.8, P25: 15.8, P50: 16.8, P75: 18.1, P90: 19.5, P97: 21.5 },
        ],
      },
      weight_for_age: {
        M: [
          { age: 120, L: 1, M: 32.0, S: 0.14, P3: 22, P10: 25, P25: 28, P50: 32, P75: 36, P90: 41, P97: 47 },
          { age: 126, L: 1, M: 34.0, S: 0.14, P3: 24, P10: 27, P25: 30, P50: 34, P75: 38, P90: 43, P97: 50 },
        ],
        F: [
          { age: 120, L: 1, M: 32.0, S: 0.14, P3: 22, P10: 25, P25: 28, P50: 32, P75: 36, P90: 41, P97: 47 },
          { age: 126, L: 1, M: 34.0, S: 0.14, P3: 24, P10: 27, P25: 30, P50: 34, P75: 38, P90: 43, P97: 50 },
        ],
      },
    },
  },
}));

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const BASE_BIRTH_DATE = "2013-09-01";

function makeRecord(overrides: Partial<AnthropometricRecord> & { id: number }): AnthropometricRecord {
  return {
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

const singleRecord = makeRecord({ id: 1 });

const parentRecord = makeRecord({
  id: 2,
  evaluation_date: "2025-07-10",
  weight_kg: 38.0,
  standing_height_cm: 148.0,
});

// ---------------------------------------------------------------------------
// Opciones axe compartidas
// ---------------------------------------------------------------------------
// "region" desactivada: el gráfico está envuelto en role="img" (no landmark region),
// lo cual es semánticamente correcto para un gráfico de datos. axe genera una
// advertencia "region" cuando detecta contenido no envuelto en landmark, pero
// en este contexto el wrapper role="img" es la alternativa WCAG intencional.
const AXE_OPTIONS = {
  rules: {
    region: { enabled: false },
  },
} as const;

// ---------------------------------------------------------------------------
// Tests WCAG 2.1 AA
// ---------------------------------------------------------------------------

describe("PercentileCurves — accesibilidad WCAG 2.1 AA", () => {
  it("no tiene violaciones con records vacíos", async () => {
    const { container } = render(
      <PercentileCurves
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        records={[]}
        indicator="height_for_age"
      />,
    );
    const results = await axe(container, AXE_OPTIONS);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones con un record (height_for_age)", async () => {
    const { container } = render(
      <PercentileCurves
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        records={[singleRecord]}
        indicator="height_for_age"
      />,
    );
    const results = await axe(container, AXE_OPTIONS);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones con bmi_for_age", async () => {
    const { container } = render(
      <PercentileCurves
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        records={[singleRecord]}
        indicator="bmi_for_age"
      />,
    );
    const results = await axe(container, AXE_OPTIONS);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones con weight_for_age + registro adicional (parent record)", async () => {
    const { container } = render(
      <PercentileCurves
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        records={[singleRecord, parentRecord]}
        indicator="weight_for_age"
      />,
    );
    const results = await axe(container, AXE_OPTIONS);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones cuando phvAgeMonths está presente (marcador PHV)", async () => {
    const { container } = render(
      <PercentileCurves
        sex="M"
        birthDate={BASE_BIRTH_DATE}
        records={[singleRecord]}
        indicator="height_for_age"
        phvAgeMonths={158}
      />,
    );
    const results = await axe(container, AXE_OPTIONS);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones con sexo femenino (F) + height_for_age", async () => {
    const femaleRecord = makeRecord({
      id: 3,
      evaluation_date: "2026-02-20",
      weight_kg: 42.0,
      standing_height_cm: 152.0,
    });
    const { container } = render(
      <PercentileCurves
        sex="F"
        birthDate={BASE_BIRTH_DATE}
        records={[femaleRecord]}
        indicator="height_for_age"
      />,
    );
    const results = await axe(container, AXE_OPTIONS);
    expect(results).toHaveNoViolations();
  });
});
