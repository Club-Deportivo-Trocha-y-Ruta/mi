/**
 * Regresión — MyAthleteDetailPage (padre) debe reflejar la medición MÁS
 * RECIENTE, no la más antigua (spec 040, defecto G-0x del audit
 * `docs/18-growth-module-redesign/proposal.md`).
 *
 * Reescrito para feature 040, US4 (T062): el tab Crecimiento ya no clasifica
 * en el cliente vía `NutritionalClassification` (`records[0]` directo) —
 * ahora monta el `GrowthTab` compartido en modo padre, cuyas tarjetas
 * familiares (`FamilyStageCard`/`FamilyBandCards`, sin mockear) leen
 * `GrowthSummary.latest`/`.stage` de `GET .../growth-summary` (servidor).
 * Esta suite ahora vigila la misma regresión de orden un nivel más arriba:
 * que el fixture MSW de `growth-summary` (que representa el cálculo del
 * servidor sobre la medición más reciente) sea lo que efectivamente se
 * pinta, y que la banda de la medición más antigua nunca aparezca.
 *
 * El backend devuelve los registros antropométricos ordenados
 * `evaluation_date` DESC (ver `backend/app/routers/anthropometry.py`, más
 * reciente primero). Este archivo NO mockea `useAnthropometry`: ejercita la
 * capa HTTP real (axios) contra un handler MSW que responde con tres
 * registros ya ordenados newest-first, igual que el backend — así el
 * segundo test detecta si la página volviera a reordenar/recortar la lista
 * antes de dársela a `GrowthCurveSection`.
 *
 * FR-016 (`contracts/growth-tab-ui.md`): la vista familiar no debe mostrar
 * Z-score/percentil/etiqueta clínica — el primer test ahora también vigila
 * eso, además de "más reciente, no más antigua".
 *
 * Privacidad Ley 1581: fixtures 100% sintéticos (ningún atleta real), sin
 * fecha de nacimiento real ni nombre de un menor real.
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/hooks/athletes/useAthlete", () => ({
  useAthlete: vi.fn(),
}));

// NO mockeamos useAnthropometry: es el objeto de esta regresión (orden de
// `records` reenviado a `GrowthCurveSection`). Tampoco mockeamos
// `FamilyStageCard`/`FamilyBandCards` (dentro de `GrowthTab`, sin mockear
// más abajo): son las que ahora reflejan "más reciente, no más antigua" a
// partir de `GrowthSummary.latest`/`.stage` — el fixture MSW de
// `growth-summary` (ver `beforeEach`) es la fuente de esa banda/etapa.
// `ResearchReferences` ya no se mockea: `GrowthTab` en modo padre no la
// monta (exclusiva del coach, `contracts/growth-tab-ui.md`).

// Sub-componentes pesados ajenos al objeto de este archivo — mismo criterio
// que MyAthleteDetailPage.test.tsx / MyAthleteDetailPage.activities.test.tsx.
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
}));
vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: () => <div data-testid="anthropometry-history">AnthropometryHistory</div>,
}));
vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: () => <div data-testid="phv-explanation-card">PHVExplanationCard</div>,
}));
vi.mock("@/components/athletes/ai/AthleteAIAnalysisTab", () => ({
  AthleteAIAnalysisTab: () => <div data-testid="mock-ai-analysis-tab" />,
}));
// GrowthCurveSection (T052 reemplazó a `GrowthCharts`): capturamos el orden
// del array `records` que la página le entrega. La página ya no deriva
// `phvAgeMonths` — eso vive dentro de `GrowthCurveSection` y lo cubre
// `growth/__tests__/GrowthCurveSection.test.tsx`; aquí se vigila que la
// página no reordene ni recorte la lista newest-first del backend, que es la
// precondición de T005 (`records[0]` = medición más reciente).
vi.mock("@/components/athletes/growth/GrowthCurveSection", () => ({
  GrowthCurveSection: ({ records }: { records: { id: number }[] }) => (
    <div data-testid="growth-curve" data-record-ids={records.map((r) => r.id).join(",")}>
      GrowthCurveSection
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de los mocks)
// ---------------------------------------------------------------------------

import { useAthlete } from "@/hooks/athletes/useAthlete";
import { MyAthleteDetailPage } from "../MyAthleteDetailPage";
import { TooltipProvider } from "@/components/ui/tooltip";
import { mswServer } from "@/test/setup";
import { makeGrowthSummary } from "@/test/msw/growthSummaryHandlers";
import { MaturationStatus, Sex } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// ---------------------------------------------------------------------------
// Fixtures — 100% sintéticos, ningún dato de un atleta real
// ---------------------------------------------------------------------------

const MY_ATHLETE_ID = 42;
// Fecha de nacimiento sintética que mantiene los tres registros dentro del
// rango de la referencia OMS 2007 (61.5–228.5 meses) — ver
// frontend/src/data/growth-reference-who.json.
const BIRTH_DATE = "2013-06-15";

const mockAthlete: AthleteDetailOut = {
  id: MY_ATHLETE_ID,
  user_id: 100,
  first_name: "Atleta",
  last_name: "Ficticio",
  birth_date: BIRTH_DATE,
  sex: Sex.M,
  club_join_date: "2023-01-01",
  years_in_club: 2.3,
  age_decimal: 13.1,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function makeRecord(overrides: Partial<AnthropometricRecord>): AnthropometricRecord {
  return {
    id: 1,
    athlete_id: MY_ATHLETE_ID,
    evaluation_date: "2026-01-15",
    weight_kg: 45.0,
    standing_height_cm: 155.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 77.0,
    leg_sitting_ratio: 0.987,
    maturity_offset: -0.3,
    age_at_phv: 12.0,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-01-15T10:00:00",
    notes: null,
    bmi: 18.7,
    bmi_z_score: -0.2,
    bmi_percentile: 42,
    weight_z_score: 0.1,
    weight_percentile: 54,
    nutritional_status: "adecuado",
    // Los Z/percentil de estas fixtures son valores "almacenados": sin
    // growth_source="WHO" el hook useGrowthMetrics (T025) los descarta y
    // recalcula en cliente, lo que ocultaría el bug de orden que prueba T004.
    growth_source: "WHO",
    ...overrides,
  };
}

// Banda "low" (Talla baja): height_z_score < -2.
const NEWEST_RECORD = makeRecord({
  id: 3,
  evaluation_date: "2026-08-01",
  height_z_score: -2.5,
  height_percentile: 1,
  age_at_phv: 13.5, // -> phvAgeMonths esperado = 162
});
const MIDDLE_RECORD = makeRecord({
  id: 2,
  evaluation_date: "2026-05-01",
  height_z_score: 0.3,
  height_percentile: 62,
  age_at_phv: 13.0,
});
// Banda "high" (Talla muy alta): height_z_score > 2.
const OLDEST_RECORD = makeRecord({
  id: 1,
  evaluation_date: "2026-01-15",
  height_z_score: 2.5,
  height_percentile: 99,
  age_at_phv: 12.0, // -> phvAgeMonths si se usara (erróneamente) = 144
});

// El backend responde ordenado por evaluation_date DESC — el fixture MSW
// replica ese orden exactamente (newest-first), no lo reordena el cliente.
const RECORDS_NEWEST_FIRST = [NEWEST_RECORD, MIDDLE_RECORD, OLDEST_RECORD];

function mockAthleteHook() {
  vi.mocked(useAthlete).mockReturnValue({
    data: mockAthlete,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useAthlete>);
}

// `FamilyBandCards` (dentro de `GrowthTab`, sin mockear) usa el tooltip de
// la tarjeta de IMC (`@/components/ui/tooltip`), que requiere un
// `TooltipProvider` ancestro — en la app real lo pone `App.tsx`; acá se
// envuelve el render, mismo criterio que `FamilyBandCards.test.tsx`.
function renderAthletePage() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/my-athletes/${MY_ATHLETE_ID}`]}>
      <QueryClientProvider client={queryClient}>
        <TooltipProvider delayDuration={0}>
          <Routes>
            <Route path="/my-athletes/:id" element={<MyAthleteDetailPage />} />
          </Routes>
        </TooltipProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

async function openGrowthTab() {
  const user = userEvent.setup();
  const tab = await screen.findByRole("button", { name: /crecimiento/i });
  await user.click(tab);
}

// ---------------------------------------------------------------------------
// Suite
// ---------------------------------------------------------------------------

// `GrowthSummary` que representa lo que el servidor calcularía sobre
// `NEWEST_RECORD` (record_id=3, banda de talla `retraso_talla` — coincide
// con `height_z_score=-2.5`, ver `lib/growth/bands.ts::BAND_VOCABULARY`).
// El punto de esta regresión ya no es "¿el cliente clasifica bien
// `records[0]`?" (eso ahora lo hace el servidor) sino "¿la página pinta lo
// que el servidor le manda para la medición más reciente, sin mezclar la
// banda de una medición vieja?" — de ahí que el fixture use explícitamente
// la banda opuesta a `OLDEST_RECORD` (`talla_alta`) para que un regreso al
// bug de orden sea detectable.
const NEWEST_SUMMARY = makeGrowthSummary({
  athlete_id: MY_ATHLETE_ID,
  latest_evaluation_date: NEWEST_RECORD.evaluation_date,
  stage: MaturationStatus.CircaPHV,
  latest: {
    record_id: NEWEST_RECORD.id,
    growth_source: "WHO",
    height: { value: 155.0, z_score: -2.5, percentile: 1, band: "retraso_talla" },
    bmi: { value: 18.7, z_score: -0.2, percentile: 42, band: "adecuado" },
    weight: null,
  },
});

describe("MyAthleteDetailPage (padre) — refleja la medición más reciente", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAthleteHook();
    mswServer.use(
      http.get("*/api/athletes/:athleteId/anthropometry", () =>
        HttpResponse.json(RECORDS_NEWEST_FIRST),
      ),
      http.get("*/api/athletes/:athleteId/growth-summary", () =>
        HttpResponse.json(NEWEST_SUMMARY),
      ),
    );
  });

  it("la tarjeta familiar de talla refleja la banda de la medición MÁS RECIENTE, no la más antigua, y sin numerales clínicos (FR-016)", async () => {
    const { container } = renderAthletePage();
    await openGrowthTab();

    // Banda de `NEWEST_RECORD` (retraso_talla → familyLabel "Por debajo del
    // rango esperado", `lib/growth/bands.ts`).
    expect(
      await screen.findByText("Por debajo del rango esperado"),
    ).toBeInTheDocument();
    // Banda de `OLDEST_RECORD` (talla_alta → "Por encima del promedio")
    // NUNCA debe aparecer — sería la señal del bug de orden invertido.
    expect(screen.queryByText("Por encima del promedio")).not.toBeInTheDocument();

    // FR-016: la vista familiar no muestra Z-score/percentil/"offset".
    const text = container.textContent ?? "";
    expect(text).not.toMatch(/Z=/);
    expect(text).not.toMatch(/P\d{1,2}\b/);
    expect(text).not.toMatch(/offset/i);
  });

  it("entrega la curva de crecimiento con los registros en orden newest-first", async () => {
    renderAthletePage();
    await openGrowthTab();

    const growthCurve = await screen.findByTestId("growth-curve");
    // Orden del backend intacto: 3 (2026-08-01) → 2 (2026-05-01) → 1 (2026-01-15).
    // Si la página volviera a asumir oldest-first, `GrowthCurveSection`
    // recibiría la lista invertida y la línea del atleta/PHV saldría del
    // registro equivocado.
    expect(growthCurve).toHaveAttribute("data-record-ids", "3,2,1");
  });

  // T073 (gate de integración, feature 040) — FR-020 llevó las tarjetas
  // superiores de esta página al `growth-summary` del servidor (T070), pero
  // esta página ES la vista familiar: FR-016 prohíbe percentiles y etiquetas
  // clínicas de etapa en cualquier superficie que ve un padre, no sólo
  // dentro del tab Crecimiento. Estas tarjetas quedan por encima de los tabs
  // y por eso escapan a `GrowthTab.parent.test.tsx` (T056).
  it("las tarjetas superiores usan lenguaje familiar: sin percentil ni etiqueta clínica de etapa (FR-016)", async () => {
    const { container } = renderAthletePage();

    // Las tarjetas se pintan desde el resumen del servidor (no desde
    // `athlete.latest_anthropometry`, que en la fixture es `null`).
    expect(await screen.findByText("155 cm")).toBeInTheDocument();

    // Etapa en lenguaje familiar, nunca la sigla clínica ("Circa-PHV").
    expect(screen.getByText("Pico de crecimiento")).toBeInTheDocument();

    const text = container.textContent ?? "";
    expect(text).not.toMatch(/PHV/);
    // `\b` no basta: en `textContent` las tarjetas quedan pegadas
    // ("P1Velocidad"), así que se busca la P de percentil seguida de dígitos
    // en cualquier posición.
    expect(text).not.toMatch(/P\d{1,2}/);
    expect(text).not.toMatch(/Z=/);
  });
});
