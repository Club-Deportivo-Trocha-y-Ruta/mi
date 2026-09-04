/**
 * GrowthTab.parent.test.tsx — feature 040, US4 (T056).
 *
 * Contrato: `specs/040-growth-module-redesign/contracts/growth-tab-ui.md`
 * (composición modo padre) + `contracts/band-vocabulary.md` (vocabulario
 * familiar). Ola 6 (US4): `FamilyStageCard`/`FamilyBandCards` (T058), el
 * preset familiar de la curva (T059) y el recableado de `GrowthTab
 * mode="parent"` (T062) se construyen en paralelo a este archivo — por eso
 * varias aserciones de aquí describen el diseño objetivo del contrato y
 * pueden fallar hasta que esas tareas aterricen; ver el reporte final para
 * el detalle de qué falla y por qué.
 *
 * A diferencia de `GrowthTab.test.tsx` (que mockea `GrowthCurveSection`
 * entero para aislar la composición de `GrowthTab`), este archivo mantiene
 * REAL la cadena `GrowthCurveSection` → `PercentileToolbar` →
 * `PercentileChart` → `PercentileInterpretationBlock` (solo se mockean
 * `recharts` y el JSON de referencia OMS, igual que
 * `PercentileChart.test.tsx`) porque las dos garantías de privacidad más
 * importantes de la vista familiar — "sin Z-score/percentil/offset en el
 * texto" y "sin toggles de eje/detalle" — viven dentro de esa cadena; con
 * `GrowthCurveSection` mockeado esas aserciones serían vacías.
 *
 * `AnthropometryHistory`, `PHVExplanationCard`, `TrainingReadiness`,
 * `MorphologyCard`, `ResearchReferences` y `NutritionalClassification` sí se
 * mockean (mismo criterio que `GrowthTab.test.tsx`): cada uno tiene sus
 * propios tests y aquí solo interesa si `GrowthTab` los monta o no en modo
 * padre.
 *
 * Privacidad Ley 1581: fixtures 100% sintéticas (ningún atleta real), sin
 * fecha de nacimiento real ni nombre de un menor real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/api/athletes", () => ({
  getAnthropometry: vi.fn(),
  createAnthropometry: vi.fn(),
}));

vi.mock("@/api/growth", () => ({
  getGrowthSummary: vi.fn(),
}));

// jsdom no implementa ResizeObserver — defensivo, igual que
// `PercentileChart.test.tsx`/`CalendarShell.test.tsx`.
if (!globalThis.ResizeObserver) {
  globalThis.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof ResizeObserver;
}

// `recharts` real no puede montar layout en jsdom — se sustituyen sus
// primitivas por stubs que preservan las props relevantes en atributos
// `data-*` (nunca en texto visible), mismo mock que `PercentileChart.test.tsx`.
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
    Tooltip: () => null,
    Legend: () => null,
    Line: ({ dataKey, hide }: { dataKey?: string; hide?: boolean }) => (
      <div data-testid={`chart-line-${dataKey}`} data-hidden={String(!!hide)} />
    ),
    ReferenceLine: () => null,
  };
});

// Filas mínimas de referencia OMS — cubren el rango de edad de ambos
// registros de las fixtures (~11.8 a ~13.5 años) para talla e IMC. Valores
// inventados, no corresponden a ningún atleta real.
vi.mock("@/data/growth-reference-who.json", () => ({
  default: {
    indicators: {
      height_for_age: {
        M: [
          { age: 138, L: 1, M: 145.0, S: 0.04, P3: 133, P10: 138, P25: 142, P50: 145, P75: 148, P90: 152, P97: 157 },
          { age: 150, L: 1, M: 152.0, S: 0.04, P3: 140, P10: 145, P25: 149, P50: 152, P75: 155, P90: 159, P97: 164 },
          { age: 162, L: 1, M: 159.0, S: 0.04, P3: 147, P10: 152, P25: 156, P50: 159, P75: 162, P90: 166, P97: 171 },
        ],
        F: [
          { age: 138, L: 1, M: 143.0, S: 0.04, P3: 131, P10: 136, P25: 140, P50: 143, P75: 146, P90: 150, P97: 155 },
          { age: 150, L: 1, M: 150.0, S: 0.04, P3: 138, P10: 143, P25: 147, P50: 150, P75: 153, P90: 157, P97: 162 },
          { age: 162, L: 1, M: 155.0, S: 0.04, P3: 143, P10: 148, P25: 152, P50: 155, P75: 158, P90: 162, P97: 167 },
        ],
      },
      bmi_for_age: {
        M: [
          { age: 138, L: 1, M: 17.0, S: 0.09, P3: 14.0, P10: 15.0, P25: 16.0, P50: 17.0, P75: 18.3, P90: 19.7, P97: 21.6 },
          { age: 150, L: 1, M: 17.6, S: 0.09, P3: 14.4, P10: 15.4, P25: 16.4, P50: 17.6, P75: 19.0, P90: 20.4, P97: 22.4 },
          { age: 162, L: 1, M: 18.2, S: 0.09, P3: 14.8, P10: 15.8, P25: 16.8, P50: 18.2, P75: 19.6, P90: 21.1, P97: 23.2 },
        ],
        F: [
          { age: 138, L: 1, M: 17.2, S: 0.09, P3: 14.1, P10: 15.1, P25: 16.1, P50: 17.2, P75: 18.5, P90: 19.9, P97: 21.8 },
          { age: 150, L: 1, M: 17.9, S: 0.09, P3: 14.6, P10: 15.6, P25: 16.6, P50: 17.9, P75: 19.3, P90: 20.7, P97: 22.7 },
          { age: 162, L: 1, M: 18.6, S: 0.09, P3: 15.0, P10: 16.0, P25: 17.0, P50: 18.6, P75: 20.0, P90: 21.5, P97: 23.6 },
        ],
      },
    },
  },
}));

vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: ({ mode }: { mode?: string }) => (
    <div data-testid="anthropometry-history" data-mode={mode}>
      AnthropometryHistory
    </div>
  ),
}));

vi.mock("@/components/athletes/MorphologyCard", () => ({
  MorphologyCard: () => <div data-testid="morphology-card">MorphologyCard</div>,
}));

vi.mock("@/components/athletes/NutritionalClassification", () => ({
  NutritionalClassification: () => (
    <div data-testid="nutritional-classification">NutritionalClassification</div>
  ),
}));

vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => (
    <div data-testid="research-references">Fuentes bibliográficas (7)</div>
  ),
}));

vi.mock("@/components/athletes/TrainingReadiness", () => ({
  TrainingReadiness: () => <div data-testid="training-readiness">TrainingReadiness</div>,
}));

vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: ({ readOnly }: { readOnly?: boolean }) => (
    <div data-testid="phv-explanation-card" data-readonly={readOnly ?? false}>
      {!readOnly && (
        <button type="button">Generar explicación</button>
      )}
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de mocks)
// ---------------------------------------------------------------------------

import { GrowthTab } from "@/components/athletes/growth/GrowthTab";
import * as athletesApi from "@/api/athletes";
import * as growthApi from "@/api/growth";
import { makeGrowthSummary } from "@/test/msw/growthSummaryHandlers";
import { MaturationStatus, Sex } from "@/types/enums";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import type { AthleteDetailOut } from "@/types/athlete.types";

// ---------------------------------------------------------------------------
// Fixtures — sintéticas, sin datos reales de atletas.
// ---------------------------------------------------------------------------

const mockAthlete: AthleteDetailOut = {
  id: 2,
  user_id: 20,
  first_name: "Atleta",
  last_name: "Ficticia",
  birth_date: "2013-03-10",
  sex: Sex.F,
  club_join_date: "2023-01-01",
  years_in_club: 2.0,
  age_decimal: 13.4,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function makeRecord(overrides: Partial<AnthropometricRecord> & { id: number }): AnthropometricRecord {
  return {
    athlete_id: 2,
    evaluation_date: "2026-08-14",
    weight_kg: 45.0,
    standing_height_cm: 150.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 72.0,
    leg_sitting_ratio: 0.923,
    maturity_offset: 0.0,
    age_at_phv: 13.4,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-08-14T10:00:00",
    notes: null,
    growth_source: "WHO",
    height_z_score: -1.66,
    height_percentile: 4.8,
    bmi: 21.9,
    bmi_z_score: 0.7,
    bmi_percentile: 75.7,
    ...overrides,
  };
}

/**
 * Medición más reciente: talla "riesgo_retraso_talla" (P4.8) — coincide con
 * `latest.height.band` del resumen mockeado abajo.
 */
const latestRecord = makeRecord({ id: 41 });

/**
 * Medición más antigua: percentil de talla muy alto (P99 ≈ z +2.3, banda
 * `talla_alta`, etiqueta familiar "Por encima del promedio") y etapa
 * Pre-PHV — deliberadamente contraria a la más reciente. Si algún
 * componente familiar leyera esta medición en vez de `summary.latest`
 * (regresión "usa el registro más antiguo"), el texto renderizado lo
 * delataría (ver aserciones "refleja la más reciente, no la más antigua").
 */
const oldestRecord = makeRecord({
  id: 30,
  evaluation_date: "2025-01-10",
  standing_height_cm: 130.0,
  height_z_score: 2.3,
  height_percentile: 99,
  maturation_status: MaturationStatus.PrePHV,
});

// API devuelve registros ordenados desc (más reciente primero) — mismo
// criterio que `GrowthTab.tsx`/`AthleteDetailPage.tsx`.
const twoRecordsNewestFirst = [latestRecord, oldestRecord];

/** Resumen de crecimiento cuyo `latest` coincide con `latestRecord`. */
function makeParentSummary(overrides: Parameters<typeof makeGrowthSummary>[0] = {}) {
  return makeGrowthSummary({
    athlete_id: 2,
    latest_evaluation_date: "2026-08-14",
    stage: MaturationStatus.CircaPHV,
    age_at_phv: 13.4,
    latest: {
      record_id: 41,
      growth_source: "WHO",
      height: { value: 150.0, z_score: -1.66, percentile: 4.8, band: "riesgo_retraso_talla" },
      bmi: { value: 21.9, z_score: 0.7, percentile: 75.7, band: "adecuado" },
      weight: null,
    },
    ...overrides,
  });
}

function renderParentTab(props: Partial<React.ComponentProps<typeof GrowthTab>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <GrowthTab athlete={mockAthlete} mode="parent" {...props} />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(athletesApi.getAnthropometry).mockResolvedValue(twoRecordsNewestFirst);
  vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(makeParentSummary());
});

// ---------------------------------------------------------------------------
// 1. Tarjetas de la familia — presentes, en orden, reflejan lo más reciente
// ---------------------------------------------------------------------------

describe("GrowthTab modo padre — tarjetas familiares", () => {
  it('expone data-testid="growth-tab" y las tarjetas "family-stage-card"/"family-band-cards"', async () => {
    renderParentTab();
    expect(screen.getByTestId("growth-tab")).toBeInTheDocument();
    expect(await screen.findByTestId("family-stage-card")).toBeInTheDocument();
    expect(await screen.findByTestId("family-band-cards")).toBeInTheDocument();
  });

  it("compone en el orden del contrato: stage card → band cards → curva familiar → IA (solo lectura) → historial (padre)", async () => {
    const { container } = renderParentTab();
    // Señal de "ya cargó" (`growth-curve` sólo aparece con `records.length > 0`,
    // es decir, tras resolver `useAnthropometry` — a diferencia de
    // `anthropometry-history`, mockeado sin estado de carga, que aparecería
    // de inmediato incluso antes de que la query resuelva) — las aserciones
    // de orden abajo son las que realmente verifican cada bloque del
    // contrato, con un mensaje de fallo específico por testid en vez de un
    // timeout genérico.
    await screen.findByTestId("growth-curve");

    const order = [
      "family-stage-card",
      "family-band-cards",
      "growth-curve",
      "phv-explanation-card",
      "anthropometry-history",
    ];
    const all = Array.from(container.querySelectorAll("[data-testid]"));
    const positions = order.map((id) => {
      const el = container.querySelector(`[data-testid="${id}"]`);
      expect(el).not.toBeNull();
      return all.indexOf(el as Element);
    });
    for (let i = 1; i < positions.length; i += 1) {
      expect(positions[i]).toBeGreaterThan(positions[i - 1]);
    }
  });

  it('usa los títulos fijos del contrato ("Etapa de desarrollo", "Estatura para su edad", "Peso para su estatura")', async () => {
    renderParentTab();
    const stageCard = await screen.findByTestId("family-stage-card");
    const bandCards = await screen.findByTestId("family-band-cards");

    expect(within(stageCard).getByText("Etapa de desarrollo")).toBeInTheDocument();
    expect(within(bandCards).getByText("Estatura para su edad")).toBeInTheDocument();
    expect(within(bandCards).getByText("Peso para su estatura")).toBeInTheDocument();
  });

  it("refleja la banda de talla de la medición MÁS RECIENTE, no la más antigua", async () => {
    renderParentTab();
    const bandCards = await screen.findByTestId("family-band-cards");

    // `riesgo_retraso_talla` (medición reciente, P4.8) — band-vocabulary.md.
    expect(within(bandCards).getByText("Un poco por debajo del promedio")).toBeInTheDocument();
    // `talla_alta` (medición antigua, P99) NO debe aparecer.
    expect(within(bandCards).queryByText("Por encima del promedio")).not.toBeInTheDocument();
  });

  it("refleja la etapa de maduración de la medición MÁS RECIENTE (Circa-PHV), no la más antigua (Pre-PHV)", async () => {
    renderParentTab();
    const stageCard = await screen.findByTestId("family-stage-card");

    // `phvParentMessage(CircaPHV, ...)` — `MyAthleteDetailPage.tsx`.
    expect(within(stageCard).getByText(/pico de crecimiento/i)).toBeInTheDocument();
    // Mensajes de Pre-PHV / Post-PHV (incorrectos si viniera del registro
    // más antiguo o de un valor por defecto) no deben aparecer.
    expect(within(stageCard).queryByText(/desarrollo temprano/i)).not.toBeInTheDocument();
    expect(within(stageCard).queryByText(/se está estabilizando/i)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 2. Privacidad — sin Z-score/percentil/offset, sin bibliografía
// ---------------------------------------------------------------------------

describe("GrowthTab modo padre — privacidad (sin numerales clínicos)", () => {
  it("el texto visible del tab NO contiene Z=, P<n> ni 'offset' (insensible a mayúsculas)", async () => {
    const { container } = renderParentTab();
    // La curva (real, sin mockear salvo `recharts`) sólo aparece una vez
    // resuelto `useAnthropometry` y termina de resolver su referencia OMS
    // (import dinámico) antes de auditar el texto — a diferencia de
    // `anthropometry-history` (mockeado, sin estado de carga), que no sirve
    // como señal de "ya cargó".
    await screen.findByTestId("growth-curve");

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/Z=/);
    expect(text).not.toMatch(/P\d{1,2}\b/);
    expect(text).not.toMatch(/offset/i);
  });

  it('NO muestra "Fuentes bibliográficas" (ResearchReferences es exclusivo del coach)', async () => {
    renderParentTab();
    await screen.findByTestId("growth-curve");
    expect(screen.queryByText(/Fuentes bibliográficas/i)).not.toBeInTheDocument();
    expect(screen.queryByTestId("research-references")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 3. Curva familiar — sin toggles de eje/detalle
// ---------------------------------------------------------------------------

describe("GrowthTab modo padre — curva sin controles de eje/detalle", () => {
  it("no ofrece el ToggleGroup de eje Cronológica/Biológica", async () => {
    renderParentTab();
    await screen.findByTestId("growth-curve");
    expect(screen.queryByRole("radio", { name: "Cronológica" })).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Biológica" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Cronológica" })).not.toBeInTheDocument();
  });

  it('no ofrece el botón "Detalle" (P10/P25/P75/P90)', async () => {
    renderParentTab();
    await screen.findByTestId("growth-curve");
    expect(screen.queryByRole("button", { name: "Detalle" })).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 4. Piezas exclusivas del coach — ausentes en modo padre
// ---------------------------------------------------------------------------

describe("GrowthTab modo padre — sin piezas exclusivas del coach", () => {
  it("no renderiza GrowthStatusRow, TrainingReadiness, MorphologyCard, MaturationTimeline ni ResearchReferences", async () => {
    renderParentTab();
    await screen.findByTestId("growth-curve");

    expect(screen.queryByTestId("growth-status-row")).not.toBeInTheDocument();
    expect(screen.queryByTestId("training-readiness")).not.toBeInTheDocument();
    expect(screen.queryByTestId("morphology-card")).not.toBeInTheDocument();
    expect(screen.queryByTestId("growth-timeline")).not.toBeInTheDocument();
    expect(screen.queryByTestId("research-references")).not.toBeInTheDocument();
  });

  it("ya NO renderiza el bloque narrativo antiguo NutritionalClassification (reemplazado por las tarjetas familiares)", async () => {
    renderParentTab();
    await screen.findByTestId("growth-curve");
    expect(screen.queryByTestId("nutritional-classification")).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// 5. Tarjeta de IA — solo lectura
// ---------------------------------------------------------------------------

describe("GrowthTab modo padre — tarjeta de IA de solo lectura", () => {
  it('monta PHVExplanationCard con readOnly=true y sin botón "Generar"', async () => {
    renderParentTab();
    const card = await screen.findByTestId("phv-explanation-card");
    expect(card).toHaveAttribute("data-readonly", "true");
    expect(screen.queryByRole("button", { name: /Generar/i })).not.toBeInTheDocument();
  });

  it('pasa mode="parent" a AnthropometryHistory', async () => {
    renderParentTab();
    const history = await screen.findByTestId("anthropometry-history");
    expect(history).toHaveAttribute("data-mode", "parent");
  });
});

// ---------------------------------------------------------------------------
// 6. Accesibilidad (jest-axe) — modo padre, con y sin mediciones
// ---------------------------------------------------------------------------

describe("GrowthTab modo padre — accesibilidad (jest-axe)", () => {
  it("sin violaciones axe con mediciones", async () => {
    const { container } = renderParentTab();
    await screen.findByTestId("growth-curve");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe sin mediciones (EmptyState)", async () => {
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
    vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(
      makeGrowthSummary({
        records_count: 0,
        latest_evaluation_date: null,
        stage: null,
        maturity_offset: null,
        age_at_phv: null,
        months_from_phv: null,
        velocity: null,
        measurement: { status: "never", interval_days: 90, next_due_date: null, days_overdue: null },
        alerts: [],
        latest: null,
      }),
    );

    const { container } = renderParentTab();
    await screen.findByText(/Aún no hay mediciones/i);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
