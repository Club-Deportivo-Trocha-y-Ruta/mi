/**
 * GrowthTab.a11y.test.tsx — feature 040, US2 (T043).
 *
 * `jest-axe` sobre `GrowthTab` ensamblado en modo coach, con y sin
 * mediciones (`contracts/growth-tab-ui.md` §Accessibility: "jest-axe: cero
 * violaciones para `GrowthTab` en ambos modos, con y sin registros").
 *
 * Mockea los mismos hijos "pesados" que `GrowthTab.test.tsx` (T041):
 * `GrowthCurveSection` (recharts, sin `ResizeObserver` en jsdom),
 * `TrainingReadiness`, `MorphologyCard`, `PHVExplanationCard`,
 * `AnthropometryHistory`, `ResearchReferences` y `NutritionalClassification`.
 * Cada uno ya tiene (o tendrá) su propia auditoría de accesibilidad por
 * separado; lo que interesa aquí es el ensamblaje nuevo de esta feature —
 * `GrowthAlerts`, `GrowthStatusRow`, `NextMeasurementCard`, `EmptyState` y
 * `ErrorState` — que sí se renderizan reales, igual que en
 * `SessionDetailPage.a11y.test.tsx`.
 *
 * Privacidad Ley 1581: fixtures 100% sintéticas (ningún atleta real), sin
 * fecha de nacimiento real ni nombre de un menor real.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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

vi.mock("@/components/athletes/AnthropometryHistory", () => ({
  AnthropometryHistory: ({ mode }: { mode?: string }) => (
    <div data-testid="anthropometry-history" data-mode={mode}>
      AnthropometryHistory
    </div>
  ),
}));

vi.mock("@/components/athletes/growth/GrowthCurveSection", () => ({
  GrowthCurveSection: () => <div data-testid="growth-curve">GrowthCurveSection</div>,
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
  ResearchReferences: () => <div data-testid="research-references">ResearchReferences</div>,
}));

vi.mock("@/components/athletes/TrainingReadiness", () => ({
  TrainingReadiness: () => <div data-testid="training-readiness">TrainingReadiness</div>,
}));

vi.mock("@/components/ai/PHVExplanationCard", () => ({
  PHVExplanationCard: ({ readOnly }: { readOnly?: boolean }) => (
    <div data-testid="phv-explanation-card" data-readonly={readOnly ?? false}>
      {!readOnly && <button type="button">Agregar medicion</button>}
    </div>
  ),
}));

// ---------------------------------------------------------------------------
// Imports de producción (después de mocks)
// ---------------------------------------------------------------------------

import { GrowthTab } from "@/components/athletes/growth/GrowthTab";
import * as athletesApi from "@/api/athletes";
import * as growthApi from "@/api/growth";
import { makeGrowthSummary, makeNeverGrowthSummary } from "@/test/msw/growthSummaryHandlers";
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
  last_name: "Prueba",
  birth_date: "2013-03-10",
  sex: Sex.M,
  club_join_date: "2023-01-01",
  years_in_club: 2.0,
  age_decimal: 12.9,
  category: "Sub-13",
  club_id: 1,
  created_at: "2023-01-01T00:00:00Z",
  latest_anthropometry: null,
};

function makeRecord(overrides: Partial<AnthropometricRecord> = {}): AnthropometricRecord {
  return {
    id: 41,
    athlete_id: 2,
    evaluation_date: "2026-08-14",
    weight_kg: 45.0,
    standing_height_cm: 150.0,
    arm_span_cm: null,
    sitting_height_cm: 78.0,
    leg_length_cm: 72.0,
    leg_sitting_ratio: 0.923,
    maturity_offset: 1.2,
    age_at_phv: 12.9,
    maturation_status: MaturationStatus.PostPHV,
    training_implications: null,
    evaluated_by: 1,
    created_at: "2026-08-14T10:00:00",
    notes: null,
    height_percentile: 4.8,
    growth_source: "WHO",
    ...overrides,
  };
}

function renderGrowthTab(props: Partial<React.ComponentProps<typeof GrowthTab>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <GrowthTab athlete={mockAthlete} mode="coach" {...props} />
    </QueryClientProvider>,
  );
}

describe("GrowthTab — accesibilidad (jest-axe)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sin violaciones axe en modo coach con mediciones (incl. avisos activos)", async () => {
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([makeRecord()]);
    vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(
      makeGrowthSummary({ alerts: ["rapid_growth", "phase_changed"] }),
    );

    const { container } = renderGrowthTab();

    // Espera a que el bloque resumen (real, no mockeado) termine de resolver
    // antes de auditar — de lo contrario axe corre sobre el skeleton.
    await screen.findByTestId("growth-status-row");
    expect(await screen.findByTestId("growth-alerts")).toBeInTheDocument();
    expect(screen.getByTestId("growth-next-measurement")).toBeInTheDocument();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe en modo coach sin mediciones (EmptyState)", async () => {
    vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
    vi.mocked(growthApi.getGrowthSummary).mockResolvedValue(makeNeverGrowthSummary());

    const { container } = renderGrowthTab();

    expect(await screen.findByText("Registra la primera medición")).toBeInTheDocument();
    expect(screen.queryByTestId("growth-status-row")).not.toBeInTheDocument();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
