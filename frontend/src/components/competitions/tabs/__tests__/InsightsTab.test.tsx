/**
 * Tests vitest — InsightsTab (tab "Insights IA" del detalle de la competencia).
 *
 * Tras eliminar el strangler `VITE_INSIGHTS_IN_COMPETITION`, el tab SIEMPRE
 * renderiza el grid scopeado a la válida (`ClubInsightsGrid`) — nunca el hub
 * RaceAnalysisPage. Estos tests fijan ese comportamiento.
 *
 * Cubre:
 *  - Renderiza el grid scopeado (data-testid="insights-tab") con cards.
 *  - Click en una card navega al perfil del atleta scopeado (no al hub).
 *  - Empty state cuando la válida no tiene insights.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

const mockUseClubInsightsByRace = vi.fn();
vi.mock("@/hooks/athletes/useClubInsightsByRace", () => ({
  useClubInsightsByRace: (...args: unknown[]) =>
    mockUseClubInsightsByRace(...args),
}));

import { InsightsTab } from "@/components/competitions/tabs/InsightsTab";

function renderTab(raceEventId = 5) {
  return render(
    <MemoryRouter>
      <InsightsTab raceEventId={raceEventId} />
    </MemoryRouter>,
  );
}

const INSIGHTS = {
  data: {
    race_event_id: 5,
    race_event_label: "Válida IV — Cali",
    total_athletes: 2,
    items: [
      {
        athlete_id: 145,
        athlete_display_name: "Isabel Quinonez",
        valida_num: 4,
        insight_id: 99,
        summary_excerpt: "Tercer lugar, progreso en frenada.",
        generated_at: "2026-05-25T19:49:00",
        confidence: "medium",
      },
      {
        athlete_id: 201,
        athlete_display_name: "Mateo Perez",
        valida_num: 4,
        insight_id: null,
        summary_excerpt: null,
        generated_at: null,
        confidence: null,
      },
    ],
  },
  isLoading: false,
  isError: false,
  refetch: vi.fn(),
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("InsightsTab (siempre grid scopeado, sin flag)", () => {
  it("scopea la query a la válida recibida por props", () => {
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    renderTab(5);
    // Primer argumento del hook = raceEventId scopeado.
    expect(mockUseClubInsightsByRace).toHaveBeenCalledWith(
      5,
      expect.objectContaining({ latestOnly: true }),
    );
  });

  it("renderiza el grid scopeado con las cards de la válida", () => {
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    renderTab(5);
    expect(screen.getByTestId("insights-tab")).toBeInTheDocument();
    expect(screen.getByTestId("insights-tab-card-145")).toBeInTheDocument();
    expect(screen.getByText(/2 atletas con análisis IA/i)).toBeInTheDocument();
    // NO debe montar el hub viejo (no hay tabs "Nuevo análisis"/"Cargar resultados").
    expect(screen.queryByText(/nuevo análisis/i)).not.toBeInTheDocument();
  });

  it("click en una card navega al perfil del atleta (scopeado, no al hub)", async () => {
    mockUseClubInsightsByRace.mockReturnValue(INSIGHTS);
    const user = userEvent.setup();
    renderTab(5);
    await user.click(screen.getByTestId("insights-tab-card-145"));
    expect(mockNavigate).toHaveBeenCalledWith(
      "/athletes/145?tab=ai_analysis&insight=99",
    );
  });

  it("muestra empty state cuando la válida no tiene insights", () => {
    mockUseClubInsightsByRace.mockReturnValue({
      data: { race_event_id: 5, total_athletes: 0, items: [] },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderTab(5);
    expect(screen.getByTestId("insights-tab")).toBeInTheDocument();
    expect(
      screen.getByText(/No hay insights generados para esta válida/i),
    ).toBeInTheDocument();
  });
});
