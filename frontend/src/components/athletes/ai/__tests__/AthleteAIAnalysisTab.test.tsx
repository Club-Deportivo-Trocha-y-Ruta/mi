/**
 * Tests vitest para AthleteAIAnalysisTab (FE-3).
 *
 * Cubre:
 *  - 5 sub-tabs renderizados en mode=coach (incluye "Lanzar").
 *  - mode=parent oculta "Lanzar".
 *  - Header del tab muestra última fecha/válida cuando hay insights.
 *  - Loading state mientras espera datos.
 *  - Click en tab cambia el contenido renderizado.
 *
 * Mockeamos los sub-componentes pesados (InsightsTimeline,
 * EvolutionChart, ComparatorPanel, DistributionChart, LaunchAnalysisForm,
 * AnalysisRunTimeline) — están testeados en sus propios specs.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/athletes/ai/InsightsTimeline", () => ({
  InsightsTimeline: ({ mode }: { mode: string }) => (
    <div data-testid="mock-insights-timeline">timeline-{mode}</div>
  ),
}));
vi.mock("@/components/athletes/ai/EvolutionChart", () => ({
  EvolutionChart: () => <div data-testid="mock-evolution-chart">evolution</div>,
}));
vi.mock("@/components/athletes/ai/ComparatorPanel", () => ({
  ComparatorPanel: () => <div data-testid="mock-comparator-panel">compare</div>,
}));
vi.mock("@/components/athletes/ai/DistributionChart", () => ({
  DistributionChart: () => (
    <div data-testid="mock-distribution-chart">distribution</div>
  ),
}));
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: ({ athleteName }: { athleteName: string }) => (
    <div data-testid="mock-launch-form">launch-{athleteName}</div>
  ),
}));
vi.mock("@/components/ai/AnalysisRunTimeline", () => ({
  AnalysisRunTimeline: ({ runId }: { runId: string }) => (
    <div data-testid="mock-run-timeline">run-{runId}</div>
  ),
}));

import { mswServer } from "@/test/setup";
import { emptyInsightsHandler } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Sebastián",
  last_name: "García",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

describe("AthleteAIAnalysisTab", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza los 5 sub-tabs en mode=coach (incluye Lanzar)", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
    });
    expect(screen.getByTestId("ai-subtab-evolution")).toBeInTheDocument();
    expect(screen.getByTestId("ai-subtab-compare")).toBeInTheDocument();
    expect(screen.getByTestId("ai-subtab-distribution")).toBeInTheDocument();
    expect(screen.getByTestId("ai-subtab-launch")).toBeInTheDocument();
  });

  it("oculta 'Lanzar' en mode=parent", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("ai-subtab-launch")).not.toBeInTheDocument();
  });

  it("muestra Skeleton mientras espera el header de último análisis", () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    // Skeleton del header (initial loading): no estamos buscando getByRole
    // porque Skeleton no tiene role, pero ai-header-summary aún no aparece.
    expect(screen.queryByTestId("ai-header-summary")).not.toBeInTheDocument();
  });

  it("muestra header con última fecha y badge de válida cuando hay insights", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-header-summary")).toBeInTheDocument();
    });
    // El header expone "Total aprobados: 2" del MSW handler default
    expect(screen.getByText(/total aprobados:\s*2/i)).toBeInTheDocument();
    // Badge "Válida 4" (header)
    expect(
      screen.getAllByText(/válida\s*4/i).length,
    ).toBeGreaterThanOrEqual(1);
  });

  it("muestra placeholder 'Sin análisis' cuando no hay insights", async () => {
    mswServer.use(emptyInsightsHandler);
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(
        screen.getByText(/sin análisis aprobados aún/i),
      ).toBeInTheDocument();
    });
  });

  it("cambia el contenido al hacer click en otro tab", async () => {
    const user = userEvent.setup();
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="coach" />);
    await waitFor(() => {
      expect(screen.getByTestId("mock-insights-timeline")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("ai-subtab-evolution"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-evolution-chart")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("ai-subtab-compare"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-comparator-panel")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("ai-subtab-distribution"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-distribution-chart")).toBeInTheDocument();
    });

    await user.click(screen.getByTestId("ai-subtab-launch"));
    await waitFor(() => {
      expect(screen.getByTestId("mock-launch-form")).toBeInTheDocument();
    });
    // LaunchAnalysisForm recibe el athleteName concatenado
    expect(
      screen.getByText(/launch-Sebastián\s+García/i),
    ).toBeInTheDocument();
  });

  it("no tiene violaciones a11y (modo coach, lista no vacía)", async () => {
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("ai-header-summary")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y (modo parent, lista vacía)", async () => {
    mswServer.use(emptyInsightsHandler);
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="parent" />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/sin análisis aprobados aún/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
