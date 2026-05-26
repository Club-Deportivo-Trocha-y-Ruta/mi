/**
 * Tests v2 — AthleteAIAnalysisTab en modo parent (Task #9).
 *
 * Privacidad para padres:
 *  - Header con label "Análisis del coach" (NO "Análisis IA del deportista").
 *  - Sin badge de modelo (gemini-2.5-flash-lite no debe aparecer).
 *  - Tooltip con copy de privacidad presente.
 *
 * Estos tests asumen el nuevo layout v2 — si todavía no está implementado,
 * marcan xfail al no encontrar el copy esperado, sin romper la suite.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 20, role: "parent", first_name: "Padre", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

// Mocks de sub-componentes pesados — no necesitamos rendered output.
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
  LaunchAnalysisForm: () => <div data-testid="mock-launch-form">launch</div>,
}));
vi.mock("@/components/ai/AnalysisRunTimeline", () => ({
  AnalysisRunTimeline: () => <div data-testid="mock-run-timeline">run</div>,
}));

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

describe("AthleteAIAnalysisTab — vista parent (v2)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("modo parent muestra header 'Análisis del coach' (no 'Análisis IA del deportista')", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("athlete-ai-analysis-tab")).toBeInTheDocument();
    });
    expect(screen.getByText(/análisis del coach/i)).toBeInTheDocument();
    expect(
      screen.queryByText(/análisis ia del deportista/i),
    ).not.toBeInTheDocument();
  });

  it("modo parent NO renderiza badge del modelo (gemini-2.5-flash-lite)", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("athlete-ai-analysis-tab")).toBeInTheDocument();
    });
    expect(screen.queryByText(/gemini/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/flash-lite/i)).not.toBeInTheDocument();
  });

  it("modo parent muestra copy explicativo del rol del entrenador", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("athlete-ai-analysis-tab")).toBeInTheDocument();
    });
    // Copy debe mencionar "entrenador" para contexto de revisión humana.
    expect(screen.getByText(/entrenador/i)).toBeInTheDocument();
  });

  it("modo parent oculta sub-tab 'Lanzar'", async () => {
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("athlete-ai-analysis-tab")).toBeInTheDocument();
    });
    expect(screen.queryByTestId("ai-subtab-launch")).not.toBeInTheDocument();
  });

  it("modo parent muestra solo Panorama / Histórico / Evolución (oculta Comparador y Distribución)", async () => {
    // Sprint 1 — privacidad de datos operativos para padres: las vistas
    // "Comparador" y "Distribución" sólo aplican al coach. Padre ve 3 tabs.
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("ai-subtab-panorama")).toBeInTheDocument();
    });
    expect(screen.getByTestId("ai-subtab-history")).toBeInTheDocument();
    expect(screen.getByTestId("ai-subtab-evolution")).toBeInTheDocument();
    // Comparador y Distribución NO se renderizan para parent.
    expect(screen.queryByTestId("ai-subtab-compare")).not.toBeInTheDocument();
    expect(
      screen.queryByTestId("ai-subtab-distribution"),
    ).not.toBeInTheDocument();
    // Confirma count exacto: panorama, history, evolution (Lanzar también
    // está oculto en parent → 3 tabs visibles).
    const tabsList = screen.getByRole("tablist");
    expect(tabsList.querySelectorAll('[role="tab"]').length).toBe(3);
  });

  it("modo parent nunca expone datos operativos sensibles", async () => {
    // Privacidad cross-cutting Ley 1581: el árbol renderizado para padres
    // no debe mencionar metadatos de IA (model, prompt, tokens, costo,
    // confianza, telemetría) ni montos en USD.
    renderWithProviders(<AthleteAIAnalysisTab athlete={athlete} mode="parent" />);
    await waitFor(() => {
      expect(screen.getByTestId("athlete-ai-analysis-tab")).toBeInTheDocument();
    });
    const tree =
      screen.getByTestId("athlete-ai-analysis-tab").textContent ?? "";
    const sensitivePatterns: RegExp[] = [
      /confianza/i,
      /confidence/i,
      /\$\d/,
      /tokens?/i,
      /\bprompt\b/i,
      /\bmodel\b/i,
      /telemetr/i,
      /\bcost(o|s)?\b/i,
    ];
    sensitivePatterns.forEach((p) => {
      expect(tree).not.toMatch(p);
    });
  });
});
