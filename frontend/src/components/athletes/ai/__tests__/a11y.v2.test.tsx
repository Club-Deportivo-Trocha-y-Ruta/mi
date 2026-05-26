/**
 * Tests de accesibilidad (jest-axe) para el layout v2 del módulo race-analysis
 * (Task #9).
 *
 * Cubre:
 *  - AthleteAIAnalysisTab en mode=coach
 *  - AthleteAIAnalysisTab en mode=parent
 *  - SeasonSummaryButton en estado enabled y disabled
 *
 * Política: 0 violaciones jest-axe.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { waitFor, screen } from "@testing-library/react";
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
  InsightsTimeline: () => <div>timeline</div>,
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

import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AthleteAIAnalysisTab } from "@/components/athletes/ai/AthleteAIAnalysisTab";
import { PanoramaView } from "@/components/athletes/ai/PanoramaView";
import { HeroLastInsightCard } from "@/components/athletes/ai/HeroLastInsightCard";
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
});
