/**
 * AthleteDetailPage.tabs.test.tsx — feature 040, US5 (T067).
 *
 * FR-020 (`spec.md`): la página del atleta debe abrir en "Info general"
 * salvo que la URL pida otro tab explícitamente — YA NO debe saltar sola al
 * tab Crecimiento en cuanto detecta registros. Las tarjetas superiores
 * (fuera de cualquier tab, visibles desde el primer render) deben mostrar
 * la etapa, la talla con percentil, la velocidad de talla y el estado de
 * la próxima medición — todo proveniente de `useGrowthSummary` (`GET
 * .../growth-summary`, MSW `growthSummaryHandlers`), no de
 * `athlete.latest_anthropometry` (comportamiento anterior a esta feature).
 *
 * Escrito ANTES de T070 (TDD, constitution Principle II): hoy debe fallar
 * en las aserciones de tab inicial y tarjetas superiores (la página aún
 * salta sola a Crecimiento y las tarjetas leen de `latest_anthropometry`,
 * que este archivo deja en `null` a propósito); T070 las hace pasar sin
 * modificar este archivo. La aserción de `?tab=growth` no depende de T070
 * — vigila que ese comportamiento (ya existente) sobreviva al refactor.
 *
 * Mismo criterio de mocks que `AthleteDetailPage.test.tsx` / `GrowthTab.test.tsx`:
 * se mockea `useAthlete` (control total del atleta) y los hijos "pesados"
 * ajenos al objeto de este archivo; `useAnthropometry` y `useGrowthSummary`
 * corren reales contra handlers MSW, igual que
 * `routes/parents/__tests__/MyAthleteDetailPage.growth.test.tsx`.
 *
 * Privacidad Ley 1581: fixtures 100% sintéticas, ningún atleta real (sin
 * nombre, fecha de nacimiento ni nota reales de un menor).
 */
import { describe, it, expect, beforeEach, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/hooks/athletes/useAthlete", () => ({
  useAthlete: vi.fn(),
}));

// Sub-componentes pesados ajenos al objeto de este archivo — mismo criterio
// que AthleteDetailPage.test.tsx / GrowthTab.test.tsx. GrowthAlerts,
// GrowthStatusRow y NextMeasurementCard quedan SIN mockear: son livianos,
// ya tienen su propia cobertura unitaria y aquí no estorban.
vi.mock("@/components/athletes/AthleteInfoCard", () => ({
  AthleteInfoCard: () => <div data-testid="athlete-info-card">InfoCard</div>,
}));
vi.mock("@/components/athletes/LinkedParentsCard", () => ({
  LinkedParentsCard: () => <div data-testid="linked-parents-card">LinkedParentsCard</div>,
}));
vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: () => <div data-testid="anthropometry-history">AnthropometryHistory</div>,
}));
vi.mock("@/components/athletes/growth/GrowthCurveSection", () => ({
  GrowthCurveSection: () => <div data-testid="growth-curve">GrowthCurveSection</div>,
}));
vi.mock("@/components/athletes/TrainingReadiness", () => ({
  TrainingReadiness: () => <div data-testid="training-readiness">TrainingReadiness</div>,
}));
vi.mock("@/components/athletes/MorphologyCard", () => ({
  MorphologyCard: () => <div data-testid="morphology-card">MorphologyCard</div>,
}));
vi.mock("@/components/athletes/ResearchReferences", () => ({
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));
vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: () => <div data-testid="phv-explanation-card">PHVExplanationCard</div>,
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de los mocks)
// ---------------------------------------------------------------------------

import { useAthlete } from "@/hooks/athletes/useAthlete";
import { AthleteDetailPage } from "../AthleteDetailPage";
import { mswServer } from "@/test/setup";
import { makeGrowthSummary } from "@/test/msw/growthSummaryHandlers";
import { MaturationStatus, Sex } from "@/types/enums";
import type { AthleteDetailOut } from "@/types/athlete.types";
import type { AnthropometricRecord } from "@/types/anthropometry.types";

// ---------------------------------------------------------------------------
// Fixtures — 100% sintéticas, ningún atleta real
// ---------------------------------------------------------------------------

const ATHLETE_ID = 8;

const mockAthlete: AthleteDetailOut = {
  id: ATHLETE_ID,
  user_id: 800,
  first_name: "Atleta",
  last_name: "Ficticio",
  birth_date: "2013-03-10",
  sex: Sex.M,
  club_join_date: "2023-01-01",
  years_in_club: 2.0,
  age_decimal: 13.0,
  category: "Sub-15",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  // Deliberadamente null: las tarjetas superiores (T070) deben leer de
  // `useGrowthSummary`, no de este campo — si una implementación futura
  // volviera a usarlo, la fila de tarjetas caería en el placeholder "Sin
  // mediciones..." y este archivo lo detectaría.
  latest_anthropometry: null,
};

function makeRecord(
  id: number,
  overrides: Partial<AnthropometricRecord> = {},
): AnthropometricRecord {
  return {
    id,
    athlete_id: ATHLETE_ID,
    evaluation_date: "2026-08-01",
    weight_kg: 45.0,
    standing_height_cm: 152.0,
    arm_span_cm: null,
    sitting_height_cm: 73.0,
    leg_length_cm: 77.0,
    leg_sitting_ratio: 1.05,
    maturity_offset: 1.2,
    age_at_phv: 12.9,
    maturation_status: MaturationStatus.CircaPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-08-01T00:00:00Z",
    notes: null,
    growth_source: "WHO",
    ...overrides,
  };
}

// Registros crudos con talla/etapa DISTINTAS de las del resumen (abajo) a
// propósito: si un tile leyera del registro en vez del resumen, este
// archivo lo detecta ("152 cm"/"145 cm"/"Circa-PHV" nunca deben aparecer en
// las tarjetas superiores).
const RECORDS = [
  makeRecord(2, { evaluation_date: "2026-08-01", standing_height_cm: 152.0 }),
  makeRecord(1, { evaluation_date: "2025-06-01", standing_height_cm: 145.0 }),
];

const SUMMARY = makeGrowthSummary({
  athlete_id: ATHLETE_ID,
  records_count: 2,
  latest_evaluation_date: "2026-08-01",
  stage: MaturationStatus.PostPHV,
  velocity: {
    cm_per_month: 0.31,
    cm_per_year: 3.7,
    window_days: 101,
    interval_short: false,
    expected_cm_per_year: [1.0, 4.0],
  },
  measurement: {
    status: "ok",
    interval_days: 120,
    next_due_date: "2026-12-12",
    days_overdue: null,
  },
  alerts: [],
  latest: {
    record_id: 2,
    growth_source: "WHO",
    height: { value: 150.0, z_score: -1.66, percentile: 4.8, band: "riesgo_retraso_talla" },
    bmi: { value: 21.9, z_score: 0.7, percentile: 75.7, band: "adecuado" },
    weight: null,
  },
});

function mockAthleteHook() {
  vi.mocked(useAthlete).mockReturnValue({
    data: mockAthlete,
    isLoading: false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof useAthlete>);
}

function renderPage(query = "") {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <MemoryRouter initialEntries={[`/athletes/${ATHLETE_ID}${query}`]}>
      <QueryClientProvider client={queryClient}>
        <Routes>
          <Route path="/athletes/:id" element={<AthleteDetailPage />} />
        </Routes>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

// ---------------------------------------------------------------------------
// Suite — FR-020
// ---------------------------------------------------------------------------

describe("AthleteDetailPage — tab inicial y tarjetas superiores (FR-020)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAthleteHook();
    mswServer.use(
      http.get("*/api/athletes/:athleteId/anthropometry", () => HttpResponse.json(RECORDS)),
      http.get("*/api/athletes/:athleteId/growth-summary", () => HttpResponse.json(SUMMARY)),
    );
  });

  it('con registros y sin "?tab" en la URL, el tab activo es "Info general" (no salta solo a Crecimiento)', async () => {
    renderPage();

    // Esperar a que los registros carguen (señal de que el efecto de
    // auto-selección, si existe, ya tuvo su oportunidad de disparar — el
    // botón "Crecimiento" sólo aparece con `records.length > 0`, la misma
    // condición que ese efecto). Se usa `findByRole` en vez de chequear
    // directamente "Datos del atleta": ese texto también es verdadero en el
    // instante inicial (antes de que resuelva la carga), lo que daría un
    // falso positivo si se leyera demasiado pronto.
    await screen.findByRole("button", { name: /Crecimiento/i });

    // Contenido del tab Info general — debe seguir ahí una vez cargó todo.
    expect(screen.getByText(/Datos del atleta/i)).toBeInTheDocument();
    // El botón "Info general" queda resaltado como el tab activo.
    expect(screen.getByRole("button", { name: /Info general/i })).toHaveClass("bg-charcoal");

    // Nada del tab Crecimiento se monta solo.
    expect(screen.queryByTestId("growth-tab")).not.toBeInTheDocument();
    expect(screen.queryByTestId("anthropometry-history")).not.toBeInTheDocument();
  });

  it("las tarjetas superiores muestran etapa, talla con percentil, velocidad y el estado de la próxima medición desde el resumen de crecimiento", async () => {
    renderPage();

    // Las tarjetas superiores viven fuera de cualquier tab (siempre
    // visibles) — se espera directamente su contenido, alimentado por
    // `useGrowthSummary` una vez resuelve el fetch MSW.
    expect(await screen.findByText("Post-PHV")).toBeInTheDocument();
    expect(screen.getByText(/150\s*cm/)).toBeInTheDocument();
    expect(screen.getByText(/P5\b/)).toBeInTheDocument();
    expect(screen.getByText(/3\.7\s*cm\/año/)).toBeInTheDocument();
    // Insignia de estado de próxima medición — vocabulario compartido de
    // `StatusBadge`/`getMeasurementStatusMeta` (`measurement.status: "ok"`).
    expect(screen.getByText("Al día")).toBeInTheDocument();

    // Nunca la talla/etapa cruda del registro (deben venir del resumen del
    // servidor, no de `athlete.latest_anthropometry` ni del registro más
    // reciente reprocesado en cliente).
    expect(screen.queryByText(/152\s*cm/)).not.toBeInTheDocument();
    expect(screen.queryByText(/145\s*cm/)).not.toBeInTheDocument();
    expect(screen.queryByText("Circa-PHV")).not.toBeInTheDocument();
  });

  it('"?tab=growth" en la URL sigue abriendo el tab Crecimiento', async () => {
    renderPage("?tab=growth");

    expect(await screen.findByTestId("growth-tab")).toBeInTheDocument();
    expect(screen.queryByText(/Datos del atleta/i)).not.toBeInTheDocument();
  });
});
