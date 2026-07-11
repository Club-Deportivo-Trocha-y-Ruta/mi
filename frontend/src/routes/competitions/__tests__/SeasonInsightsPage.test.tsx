/**
 * Tests vitest — SeasonInsightsPage (PR3 unificación /competitions).
 *
 * Cubre:
 *  - Renderiza tabla con filas ordenadas por puntos.
 *  - Click en fila navega al detalle del deportista.
 *  - Empty state cuando no hay resultados.
 *  - Error state + reintentar.
 *  - Año inválido.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { mswServer } from "@/test/setup";
import {
  seasonPanoramaHandler,
  emptySeasonPanoramaHandler,
  errorSeasonPanoramaHandler,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { SeasonInsightsPage } from "@/routes/competitions/SeasonInsightsPage";

const mockNavigate = vi.fn();
let mockYear = "2026";
vi.mock("react-router-dom", async () => {
  const actual =
    await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useParams: () => ({ year: mockYear }),
    useNavigate: () => mockNavigate,
    Link: actual.Link,
  };
});

beforeEach(() => {
  vi.clearAllMocks();
  mockYear = "2026";
});

describe("SeasonInsightsPage", () => {
  it("renderiza la tabla con deportistas ordenados por puntos", async () => {
    mswServer.use(seasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />);

    await waitFor(() =>
      expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
    );
    expect(screen.getByText("Juan Garcia")).toBeInTheDocument();
    expect(screen.getByText("Maria Perez")).toBeInTheDocument();

    // Primera fila de datos es el de más puntos (144 = 60pts).
    const rows = screen.getAllByTestId(/^season-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "season-row-144");
  });

  it("click en fila navega al detalle del deportista (tab ai_analysis)", async () => {
    mswServer.use(seasonPanoramaHandler);
    const user = userEvent.setup();
    renderWithProviders(<SeasonInsightsPage />);

    await waitFor(() =>
      expect(screen.getByTestId("season-row-144")).toBeInTheDocument(),
    );
    await user.click(screen.getByTestId("season-row-144"));
    expect(mockNavigate).toHaveBeenCalledWith(
      "/athletes/144?tab=ai_analysis",
    );
  });

  it("muestra empty state cuando no hay resultados", async () => {
    mswServer.use(emptySeasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-empty")).toBeInTheDocument(),
    );
  });

  it("muestra error state cuando el endpoint falla", async () => {
    mswServer.use(errorSeasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />);
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-error")).toBeInTheDocument(),
    );
  });

  it("año inválido muestra alerta sin disparar fetch", async () => {
    mockYear = "abc";
    renderWithProviders(<SeasonInsightsPage />);
    expect(screen.getByText(/Año de temporada inválido/i)).toBeInTheDocument();
    expect(screen.queryByTestId("season-insights-table")).not.toBeInTheDocument();
  });
});
