/**
 * Tests de accesibilidad (jest-axe) para el layout v2 del módulo race-analysis
 * (Task #9 + Sprint 2 BB1/BB2/BB4).
 *
 * Cubre:
 *  - AthleteAIAnalysisTab en mode=coach
 *  - AthleteAIAnalysisTab en mode=parent
 *  - SeasonSummaryButton en estado enabled y disabled
 *  - PanoramaView coach/parent (Sprint 1)
 *  - HeroLastInsightCard coach/parent (Sprint 1)
 *  - Sprint 2: action bar visible (BB4), Timeline agrupado (BB1),
 *    MiniSparkline con/sin datos (BB2).
 *
 * Política: 0 violaciones jest-axe.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { waitFor, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";

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
  InsightsTimeline: ({
    mode,
    onToggleSelection,
    newsletterSelection,
  }: {
    mode: string;
    onToggleSelection?: (id: number) => void;
    newsletterSelection?: Set<number>;
  }) => (
    <div data-testid="mock-insights-timeline">
      timeline-{mode}
      {onToggleSelection && (
        <button
          type="button"
          data-testid="a11y-toggle-101"
          aria-pressed={newsletterSelection?.has(101) ?? false}
          onClick={() => onToggleSelection(101)}
        >
          Seleccionar análisis 101
        </button>
      )}
    </div>
  ),
}));
vi.mock("@/components/athletes/ai/EvolutionChart", () => ({
  EvolutionChart: () => <div>evolution</div>,
}));
vi.mock("@/components/athletes/ai/ComparatorPanel", () => ({
  ComparatorPanel: () => <div>compare</div>,
}));
vi.mock("@/components/athletes/ai/DistributionChart", () => ({
  DistributionChart: () => <div>distribution</div>,
}));
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: () => <div>launch</div>,
}));
vi.mock("@/components/ai/AnalysisRunTimeline", () => ({
  AnalysisRunTimeline: () => <div>run</div>,
}));

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import { PanoramaView } from "@/components/athletes/ai/PanoramaView";
import { HeroLastInsightCard } from "@/components/athletes/ai/HeroLastInsightCard";
import { MiniSparkline } from "@/components/athletes/ai/MiniSparkline";
import { SeasonSummaryButton } from "@/components/athletes/ai/SeasonSummaryButton";
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

describe("a11y — race-analysis v2 layout", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("AthleteAIAnalysisTab mode=coach sin violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
    );
    await waitFor(() => {
      expect(container.querySelector('[data-testid="athlete-ai-analysis-tab"]')).toBeTruthy();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("AthleteAIAnalysisTab mode=parent sin violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="parent" />,
    );
    await waitFor(() => {
      expect(container.querySelector('[data-testid="athlete-ai-analysis-tab"]')).toBeTruthy();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("SeasonSummaryButton disabled sin violaciones a11y (incl. tooltip wrapping)", async () => {
    const { container } = renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={1} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("SeasonSummaryButton enabled sin violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <SeasonSummaryButton athleteId={42} analyzedValidasCount={5} />,
    );
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // ------------------------------------------------------------------
  // Sprint 1 — PanoramaView + HeroLastInsightCard (default tab)
  // ------------------------------------------------------------------

  it("PanoramaView mode=coach sin violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="coach"
        onOpenDetail={() => undefined}
        onAddToNewsletter={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("PanoramaView mode=parent sin violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <PanoramaView
        athlete={athlete}
        mode="parent"
        onOpenDetail={() => undefined}
        onAddToNewsletter={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("HeroLastInsightCard mode=coach sin violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <HeroLastInsightCard
        athlete={athlete}
        mode="coach"
        onOpenDetail={() => undefined}
        onAddToNewsletter={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("HeroLastInsightCard mode=parent sin violaciones a11y", async () => {
    const { container } = renderWithProviders(
      <HeroLastInsightCard
        athlete={athlete}
        mode="parent"
        onOpenDetail={() => undefined}
        onAddToNewsletter={() => undefined}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // ------------------------------------------------------------------
  // Sprint 2 — multi-select action bar + MiniSparkline + Sheet abierto
  // ------------------------------------------------------------------

  it("AthleteAIAnalysisTab coach con action bar visible (BB4) sin violaciones a11y", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
    );
    await waitFor(() => {
      expect(
        container.querySelector('[data-testid="athlete-ai-analysis-tab"]'),
      ).toBeTruthy();
    });
    await user.click(screen.getByTestId("ai-subtab-history"));
    await waitFor(() => {
      expect(screen.getByTestId("a11y-toggle-101")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("a11y-toggle-101"));
    await waitFor(() => {
      expect(screen.getByTestId("newsletter-action-bar")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("AthleteAIAnalysisTab coach con Sheet del Comparador abierto (BB3) sin violaciones a11y", async () => {
    const user = userEvent.setup();
    const { container } = renderWithProviders(
      <AthleteAIAnalysisTab athlete={athlete} mode="coach" />,
    );
    await waitFor(() => {
      expect(
        container.querySelector('[data-testid="athlete-ai-analysis-tab"]'),
      ).toBeTruthy();
    });
    await user.click(screen.getByTestId("ai-subtab-distribution"));
    await waitFor(() => {
      expect(screen.getByTestId("open-comparator-sheet")).toBeInTheDocument();
    });
    await user.click(screen.getByTestId("open-comparator-sheet"));
    await waitFor(() => {
      expect(
        screen.getByText(/comparador de progreso/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("MiniSparkline empty state (<2 puntos) sin violaciones a11y", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/evolution", () =>
        HttpResponse.json({
          season: 2026,
          metric: "ranking",
          confidence: "low",
          series: [
            {
              valida_num: 1,
              event_id: 91,
              event_date: "2026-01-31",
              value: 5,
              unit: null,
            },
          ],
        }),
      ),
    );
    const { container } = renderWithProviders(<MiniSparkline athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByText(/al menos 2 análisis/i)).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("MiniSparkline con datos (≥2 puntos) sin violaciones a11y", async () => {
    // Handler default ya devuelve 4 puntos — esperamos a que pase el
    // loading skeleton (aria-busy="true") al estado con datos.
    const { container } = renderWithProviders(<MiniSparkline athleteId={42} />);
    await waitFor(() => {
      const wrapper = screen.getByTestId("mini-evolution-sparkline");
      // El skeleton inicial tiene aria-busy="true"; el chart final no.
      expect(wrapper).not.toHaveAttribute("aria-busy", "true");
    });
    // Confirmamos que el contenedor renderiza el aria-label (no es chart "huérfano").
    expect(
      screen.getByLabelText(/Sparkline de evolución de posición/i),
    ).toBeInTheDocument();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  // ------------------------------------------------------------------
  // Sprint 2 BB1 — InsightsTimeline agrupado (importa el componente real)
  // ------------------------------------------------------------------

  // NOTA: a11y del Timeline agrupado real está cubierta en
  // InsightsTimeline.grouped.test.tsx — aquí no se importa para evitar
  // conflicto con el mock global de InsightsTimeline declarado arriba.
});
