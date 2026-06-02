/**
 * Tests vitest — ClubInsightsPage (PR3 unificación /competitions).
 *
 * Cubre:
 *  - Selector de válida poblado desde useRaceEventsList.
 *  - Grid de insights del club para la válida seleccionada.
 *  - Click en card navega al detalle del deportista bajo /competitions/insights.
 *  - Empty / error states.
 *
 * Mockeamos los hooks de datos para aislar el wiring de la página.
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
    Link: actual.Link,
  };
});

const mockUseRaceEventsList = vi.fn();
vi.mock("@/hooks/race/useRaceEvents", () => ({
  useRaceEventsList: () => mockUseRaceEventsList(),
}));

const mockUseClubInsightsByRace = vi.fn();
vi.mock("@/hooks/athletes/useClubInsightsByRace", () => ({
  useClubInsightsByRace: (...args: unknown[]) =>
    mockUseClubInsightsByRace(...args),
}));

import { ClubInsightsPage } from "@/routes/competitions/insights/ClubInsightsPage";

function renderPage() {
  return render(
    <MemoryRouter>
      <ClubInsightsPage />
    </MemoryRouter>,
  );
}

const EVENTS = {
  data: {
    items: [
      { id: 5, sequence_number: 4, name: "Válida IV", status: "completed" },
      { id: 6, sequence_number: 5, name: "Válida V", status: "scheduled" },
    ],
  },
  isLoading: false,
};

beforeEach(() => {
  vi.clearAllMocks();
});

describe("ClubInsightsPage", () => {
  it("puebla el selector y muestra el grid de la primera válida", () => {
    mockUseRaceEventsList.mockReturnValue(EVENTS);
    mockUseClubInsightsByRace.mockReturnValue({
      data: {
        total_athletes: 1,
        items: [
          {
            athlete_id: 144,
            athlete_display_name: "Juan Garcia",
            valida_num: 4,
            insight_id: 99,
            summary_excerpt: "Buen progreso.",
            generated_at: "2026-05-25T19:49:00",
            confidence: "high",
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });

    renderPage();

    const select = screen.getByTestId(
      "club-insights-race-select",
    ) as HTMLSelectElement;
    expect(select).toBeInTheDocument();
    // Default = primera válida (id 5).
    expect(select.value).toBe("5");
    expect(screen.getByTestId("club-insights-grid")).toBeInTheDocument();
    expect(screen.getByText("Juan Garcia")).toBeInTheDocument();
  });

  it("click en card navega al detalle del deportista", async () => {
    mockUseRaceEventsList.mockReturnValue(EVENTS);
    mockUseClubInsightsByRace.mockReturnValue({
      data: {
        total_athletes: 1,
        items: [
          {
            athlete_id: 144,
            athlete_display_name: "Juan Garcia",
            valida_num: 4,
            insight_id: 99,
            summary_excerpt: "Buen progreso.",
            generated_at: "2026-05-25T19:49:00",
            confidence: "high",
          },
        ],
      },
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    const user = userEvent.setup();
    renderPage();

    await user.click(screen.getByTestId("club-insight-card-144"));
    expect(mockNavigate).toHaveBeenCalledWith(
      "/competitions/insights/athletes/144",
    );
  });

  it("muestra empty state sin válidas", () => {
    mockUseRaceEventsList.mockReturnValue({ data: { items: [] }, isLoading: false });
    mockUseClubInsightsByRace.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: false,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByTestId("club-insights-no-races")).toBeInTheDocument();
  });

  it("muestra error state cuando falla la carga de insights", () => {
    mockUseRaceEventsList.mockReturnValue(EVENTS);
    mockUseClubInsightsByRace.mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
      refetch: vi.fn(),
    });
    renderPage();
    expect(screen.getByTestId("club-insights-error")).toBeInTheDocument();
  });
});
