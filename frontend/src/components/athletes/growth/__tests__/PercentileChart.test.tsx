/**
 * Tests — PercentileChart (feature 040, T047/US3).
 *
 * `PercentileChart` es la mitad "gráfica" de la antigua `PercentileCurves.tsx`
 * (T050 la extrae y le agrega `axis`/`range`/`detail`/`preset` como props
 * controladas por `GrowthCurveSection`, en vez de estado propio). Este
 * archivo fija el contrato documentado en
 * `specs/040-growth-module-redesign/contracts/growth-tab-ui.md`:
 *   - envoltorio accesible `role="img"` con `aria-label` que resume indicador
 *     y cantidad de mediciones (alternativa visible = `PercentileTable`);
 *   - el marcador de maduración porta la etiqueta PHV/PWV según indicador y
 *     sexo (idéntico a `getMaturationMarker` de `PercentileCurves.tsx`);
 *   - `detail` controla la visibilidad de las líneas P10/P25/P75/P90 (P50,
 *     P3, P97 y la línea del atleta siempre se muestran).
 *
 * El componente carga las filas de referencia OMS con un `import()` dinámico
 * dentro de un efecto/memo — por eso las aserciones usan `findBy*` (esperan
 * al menos un tick) en vez de `getBy*`.
 *
 * Mocks: `recharts` (jsdom no implementa `ResizeObserver`/layout real — mismo
 * criterio que `PercentileCurves.test.tsx`/`GrowthCharts.test.tsx`) y el JSON
 * de referencia OMS. `Line` expone `dataKey`/`hide` y `ReferenceLine` expone
 * `label`, igual que `PercentileCurves.characterization.test.tsx`.
 *
 * Datos: sintéticos, sin nombres ni fechas de nacimiento reales de menores.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import { PercentileChart } from "@/components/athletes/growth/PercentileChart";
import { MaturationStatus } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { GrowthIndicator } from "@/lib/growth/lms";

// Defensivo: jsdom no implementa ResizeObserver. recharts se mockea por
// completo abajo así que no debería invocarse, pero algunos entornos de CI
// instancian ResponsiveContainer antes del mock — mismo guard que
// CalendarShell.test.tsx.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

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
    XAxis: ({ tickFormatter }: { tickFormatter?: (v: number) => string }) => (
      <div
        data-testid="x-axis"
        data-sample-180={tickFormatter ? tickFormatter(180) : ""}
      />
    ),
    YAxis: () => null,
    Area: () => null,
    Tooltip: () => null,
    Legend: () => null,
    Line: ({ dataKey, hide }: { dataKey?: string; hide?: boolean }) => (
      <div data-testid={`chart-line-${dataKey}`} data-hidden={String(!!hide)} />
    ),
    ReferenceLine: ({ label }: { label?: { value?: string } | string }) => {
      const value = typeof label === "string" ? label : label?.value;
      return value ? <div data-testid="marker-label">{value}</div> : null;
    },
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

const singleRecord = makeRecord({ id: 1 });

interface Overrides {
  indicator?: GrowthIndicator;
  sex?: "M" | "F";
  records?: AnthropometricRecord[];
  phvAgeMonths?: number;
  axis?: "chrono" | "bio";
  range?: "window" | "full";
  detail?: boolean;
  preset?: "coach" | "family";
}

function renderChart(overrides: Overrides = {}) {
  return render(
    <PercentileChart
      indicator={overrides.indicator ?? "height_for_age"}
      records={overrides.records ?? [singleRecord]}
      sex={overrides.sex ?? "M"}
      birthDate={BASE_BIRTH_DATE}
      phvAgeMonths={overrides.phvAgeMonths}
      axis={overrides.axis ?? "chrono"}
      range={overrides.range ?? "window"}
      detail={overrides.detail ?? false}
      preset={overrides.preset}
    />,
  );
}

// ---------------------------------------------------------------------------
// 1. role="img" + aria-label accesible
// ---------------------------------------------------------------------------

describe("PercentileChart — envoltorio accesible", () => {
  it("expone role=img con un aria-label no vacío una vez resuelta la referencia OMS", async () => {
    renderChart({ records: [singleRecord] });
    const img = await screen.findByRole("img");
    const label = img.getAttribute("aria-label");
    expect(label).toBeTruthy();
    expect(label).toMatch(/1/); // 1 medición
  });

  it("el aria-label no incluye la fecha de nacimiento completa del atleta (privacidad)", async () => {
    renderChart({ records: [singleRecord] });
    const img = await screen.findByRole("img");
    expect(img.getAttribute("aria-label")).not.toContain(BASE_BIRTH_DATE);
  });

  it("con 0 registros no lanza error y mantiene el rol de imagen (curvas de referencia solas)", async () => {
    expect(() => renderChart({ records: [] })).not.toThrow();
    const img = await screen.findByRole("img");
    expect(img).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 2. Ejes/rango — smoke tests (axis/range no deben romper el render)
// ---------------------------------------------------------------------------

describe("PercentileChart — combinaciones de axis/range", () => {
  it("axis='bio' con phvAgeMonths definido no lanza error", async () => {
    expect(() =>
      renderChart({ axis: "bio", phvAgeMonths: 158 }),
    ).not.toThrow();
    expect(await screen.findByRole("img")).toBeInTheDocument();
  });

  it("range='full' no lanza error", async () => {
    expect(() => renderChart({ range: "full" })).not.toThrow();
    expect(await screen.findByRole("img")).toBeInTheDocument();
  });

  it("preset='family' no lanza error", async () => {
    expect(() => renderChart({ preset: "family" })).not.toThrow();
    expect(await screen.findByRole("img")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 2b. Re-etiquetado de ticks del eje X al activar el eje biológico —
//     re-homed de `PercentileCurves.characterization.test.tsx` (T011/T052):
//     el gating por rol/indicador ahora vive en `GrowthCurveSection`
//     (`GrowthCurveSection.test.tsx` — "gating del eje cronológico/
//     biológico"), pero el formato del tick sigue siendo responsabilidad de
//     `PercentileChart` (`xTickFormatter`).
// ---------------------------------------------------------------------------

describe("PercentileChart — formato de ticks del eje X según axis", () => {
  it("axis='chrono': 180 meses se muestra como '15.0 a'", async () => {
    renderChart({ axis: "chrono", phvAgeMonths: 156 });
    expect(await screen.findByTestId("x-axis")).toHaveAttribute(
      "data-sample-180",
      "15.0 a",
    );
  });

  it("axis='bio' con phvAgeMonths=156: 180 meses se re-etiqueta a offset relativo '+2.0 a'", async () => {
    renderChart({ axis: "bio", phvAgeMonths: 156 });
    expect(await screen.findByTestId("x-axis")).toHaveAttribute(
      "data-sample-180",
      "+2.0 a",
    );
  });
});

// ---------------------------------------------------------------------------
// 3. detail — visibilidad de P10/P25/P75/P90
// ---------------------------------------------------------------------------

describe("PercentileChart — toggle de detalle", () => {
  it("detail=false oculta (o no monta) P10/P25/P75/P90, pero conserva P50", async () => {
    renderChart({ detail: false });
    const p50 = await screen.findByTestId("chart-line-P50");
    expect(p50.getAttribute("data-hidden")).not.toBe("true");

    for (const key of ["P10", "P25", "P75", "P90"]) {
      const line = screen.queryByTestId(`chart-line-${key}`);
      const isHiddenOrAbsent = line === null || line.getAttribute("data-hidden") === "true";
      expect(isHiddenOrAbsent).toBe(true);
    }
  });

  it("detail=true muestra P10/P25/P75/P90", async () => {
    renderChart({ detail: true });
    for (const key of ["P10", "P25", "P75", "P90"]) {
      const line = await screen.findByTestId(`chart-line-${key}`);
      expect(line.getAttribute("data-hidden")).not.toBe("true");
    }
  });
});

// ---------------------------------------------------------------------------
// 4. Marcador de maduración — etiqueta PHV/PWV (port de getMaturationMarker)
// ---------------------------------------------------------------------------

describe("PercentileChart — marcador PHV/PWV", () => {
  it("talla (height_for_age): etiqueta PHV", async () => {
    renderChart({ indicator: "height_for_age", phvAgeMonths: 156, records: [] });
    expect(await screen.findByTestId("marker-label")).toHaveTextContent("PHV");
  });

  it("IMC (bmi_for_age): etiqueta PHV, igual que talla", async () => {
    renderChart({ indicator: "bmi_for_age", phvAgeMonths: 140, records: [] });
    expect(await screen.findByTestId("marker-label")).toHaveTextContent("PHV");
  });

  it("peso (weight_for_age) en hombres: etiqueta PHV/PWV (coinciden)", async () => {
    renderChart({
      indicator: "weight_for_age",
      sex: "M",
      phvAgeMonths: 156,
      records: [],
    });
    expect(await screen.findByTestId("marker-label")).toHaveTextContent("PHV/PWV");
  });

  it("peso (weight_for_age) en mujeres: etiqueta PWV desplazada, sin PHV", async () => {
    renderChart({
      indicator: "weight_for_age",
      sex: "F",
      phvAgeMonths: 140,
      records: [],
    });
    const marker = await screen.findByTestId("marker-label");
    expect(marker).toHaveTextContent("PWV");
    expect(marker).not.toHaveTextContent("PHV/PWV");
  });

  it("sin phvAgeMonths no hay marcador de maduración", async () => {
    renderChart({ phvAgeMonths: undefined, records: [] });
    await screen.findByRole("img");
    expect(screen.queryByTestId("marker-label")).not.toBeInTheDocument();
  });
});
