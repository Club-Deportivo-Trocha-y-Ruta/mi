/**
 * Regresión — MyAthleteDetailPage (padre) debe clasificar la medición MÁS
 * RECIENTE, no la más antigua (spec 040, defecto G-0x del audit
 * `docs/18-growth-module-redesign/proposal.md`).
 *
 * El backend devuelve los registros antropométricos ordenados
 * `evaluation_date` DESC (ver `backend/app/routers/anthropometry.py`, más
 * reciente primero). Este archivo NO mockea `useAnthropometry`: ejercita la
 * capa HTTP real (axios) contra un handler MSW que responde con tres
 * registros ya ordenados newest-first, igual que el backend — así el test
 * detecta si el componente vuelve a asumir el orden equivocado (`records.at(-1)`
 * en vez de `records[0]`).
 *
 * Antes del fix (T005): el componente usaba `records[records.length - 1]`
 * (el registro más antiguo) tanto para `NutritionalClassification` como para
 * `phvAgeMonths` — este test falla contra ese código.
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

// NO mockeamos useAnthropometry ni NutritionalClassification: son el objeto
// de esta regresión (orden de records + clasificación resultante).

// Sub-componentes pesados ajenos al objeto de este archivo — mismo criterio
// que MyAthleteDetailPage.test.tsx / MyAthleteDetailPage.activities.test.tsx.
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
}));
vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: () => <div data-testid="anthropometry-history">AnthropometryHistory</div>,
}));
vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
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
import { mswServer } from "@/test/setup";
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
        <Routes>
          <Route path="/my-athletes/:id" element={<MyAthleteDetailPage />} />
        </Routes>
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

describe("MyAthleteDetailPage (padre) — clasifica la medición más reciente", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAthleteHook();
    mswServer.use(
      http.get("*/api/athletes/:athleteId/anthropometry", () =>
        HttpResponse.json(RECORDS_NEWEST_FIRST),
      ),
    );
  });

  it("usa el registro más reciente (records[0]) para la clasificación nutricional, no el más antiguo", async () => {
    renderAthletePage();
    await openGrowthTab();

    // Banda del registro MÁS RECIENTE (height_z_score = -2.5 → "Talla baja").
    expect(await screen.findByText("Talla baja")).toBeInTheDocument();
    // Banda del registro MÁS ANTIGUO (height_z_score = +2.5 → "Talla muy
    // alta") NUNCA debe aparecer — sería la señal del bug de orden invertido.
    expect(screen.queryByText("Talla muy alta")).not.toBeInTheDocument();

    // El Z-score mostrado debe corresponder al registro más reciente.
    expect(screen.getByText(/Z=-2\.50/)).toBeInTheDocument();
    expect(screen.queryByText(/Z=\+2\.50/)).not.toBeInTheDocument();
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
});
