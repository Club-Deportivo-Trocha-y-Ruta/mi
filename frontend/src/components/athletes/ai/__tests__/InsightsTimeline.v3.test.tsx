/**
 * InsightsTimeline — insights v3 estructurados (feature 037, T301).
 *
 * Cubre:
 * - Preview de la card usa `insight.headline` cuando está presente.
 * - El drawer renderiza `<InsightV3Card>` cuando `insight.structured`
 *   viene en el detalle (en vez del parsing markdown v2/legacy).
 * - mode="parent" oculta los bloques coach-only dentro del drawer
 *   (delegado a InsightV3Card — ver InsightV3Card.test.tsx para el
 *   detalle exhaustivo de ese gating).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

import { mswServer } from "@/test/setup";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsTimeline } from "@/components/athletes/ai/InsightsTimeline";
import { mockInsightV3, mockInsightV3Detail } from "@/test/fixtures/insightV3";

const ATHLETE_ID = 42;

function insightsListHandler() {
  return http.get(
    "*/api/athletes/:athleteId/race-analysis/insights",
    () => {
      const items = [mockInsightV3()];
      return HttpResponse.json({ items, total: 1, limit: 50, offset: 0 });
    },
  );
}

function insightDetailHandler() {
  return http.get(
    "*/api/athletes/:athleteId/race-analysis/insights/:insightId",
    ({ params }) =>
      HttpResponse.json(mockInsightV3Detail({ id: Number(params.insightId) })),
  );
}

describe("InsightsTimeline — v3 (structured)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("la preview de la card usa insight.headline", async () => {
    mswServer.use(insightsListHandler());
    renderWithProviders(<InsightsTimeline athleteId={ATHLETE_ID} mode="coach" />);

    const insight = mockInsightV3();
    await waitFor(() => {
      expect(
        screen.getByTestId(`insight-card-${insight.id}`),
      ).toHaveTextContent(insight.headline!);
    });
  });

  it("el drawer (mode=coach) renderiza InsightV3Card con footer CoachAnswerForm cuando insight.structured está presente", async () => {
    mswServer.use(insightsListHandler(), insightDetailHandler());
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={ATHLETE_ID} mode="coach" />);

    const insight = mockInsightV3();
    await user.click(await screen.findByTestId(`insight-card-${insight.id}`));

    expect(await screen.findByTestId("insight-v3-card")).toBeInTheDocument();
    expect(screen.getByTestId("insight-v3-coach-question")).toBeInTheDocument();
    expect(screen.getByTestId("coach-answer-form")).toBeInTheDocument();
  });

  it("el drawer (mode=parent) renderiza InsightV3Card sin la pregunta del coach ni el footer", async () => {
    mswServer.use(insightsListHandler(), insightDetailHandler());
    const user = userEvent.setup();
    renderWithProviders(<InsightsTimeline athleteId={ATHLETE_ID} mode="parent" />);

    const insight = mockInsightV3();
    await user.click(await screen.findByTestId(`insight-card-${insight.id}`));

    expect(await screen.findByTestId("insight-v3-card")).toBeInTheDocument();
    expect(screen.queryByTestId("insight-v3-coach-question")).not.toBeInTheDocument();
    expect(screen.queryByTestId("coach-answer-form")).not.toBeInTheDocument();
  });
});
