/**
 * Tests vitest — SeasonInsightsPage (PR3 unificación /competitions).
 *
 * Cubre:
 *  - Renderiza tabla con filas ordenadas por puntos.
 *  - Click en fila navega al detalle del deportista.
 *  - Empty state cuando no hay resultados.
 *  - Error state + reintentar.
 *  - Año inválido.
 *  - Wave 3 (hotfix multicopa, 2026-09-16): con una sola copa la tabla se ve
 *    igual que antes (sin selector, ver casos arriba); con 2+ copas aparece
 *    un selector y las cifras nunca son la suma cross-copa deprecada.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";

import { mswServer } from "@/test/setup";
import {
  seasonPanoramaHandler,
  seasonPanoramaMultiCupHandler,
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

// Ruta real de la página bajo prueba — debe coincidir con `mockYear` para que
// SiblingViewTabs (que lee `useLocation`, no mockeado) resuelva la pastilla activa.
const SEASON_PATH = "/competitions/insights/season/2026";

describe("SeasonInsightsPage", () => {
  it("renderiza la tabla con deportistas ordenados por puntos", async () => {
    mswServer.use(seasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });

    await waitFor(() =>
      expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
    );
    expect(screen.getByText("Juan Garcia")).toBeInTheDocument();
    expect(screen.getByText("Maria Perez")).toBeInTheDocument();

    // Primera fila de datos es el de más puntos (144 = 60pts).
    const rows = screen.getAllByTestId(/^season-row-/);
    expect(rows[0]).toHaveAttribute("data-testid", "season-row-144");

    // Wave 3 — una sola copa (fixture `by_series` de una entrada): sin
    // selector, se ve igual que antes del hotfix.
    expect(
      screen.queryByTestId("season-insights-series-select"),
    ).not.toBeInTheDocument();
  });

  describe("Wave 3 — selector de copa (hotfix multicopa)", () => {
    it("con 2+ copas muestra el selector y las cifras cambian según la copa elegida", async () => {
      mswServer.use(seasonPanoramaMultiCupHandler);
      const user = userEvent.setup();
      renderWithProviders(<SeasonInsightsPage />, {
        initialEntries: [SEASON_PATH],
      });

      await waitFor(() =>
        expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
      );
      const select = screen.getByTestId(
        "season-insights-series-select",
      ) as HTMLSelectElement;
      expect(select).toBeInTheDocument();

      // Default: primera copa vista (Copa Valle, series_id=12) — Juan Garcia
      // corrió 2 válidas de esa copa, no las 3 de la suma cross-copa.
      const rowJuan = screen.getByTestId("season-row-144");
      expect(rowJuan).toHaveTextContent("2"); // races de Copa Valle
      expect(rowJuan).not.toHaveTextContent("100"); // total_points (deprecado)

      // Cambia a Copa Let's GO (series_id=55) — solo Juan Garcia la corrió.
      await user.selectOptions(select, "55");
      await waitFor(() => {
        expect(screen.getByTestId("season-row-144")).toHaveTextContent("40");
      });
      // Maria Perez no disputó Let's GO — fila en ceros/— , no desaparece.
      const rowMaria = screen.getByTestId("season-row-145");
      expect(rowMaria).toHaveTextContent("—");
    });

    it("a11y: el selector de copa no introduce violaciones", async () => {
      mswServer.use(seasonPanoramaMultiCupHandler);
      const { container } = renderWithProviders(<SeasonInsightsPage />, {
        initialEntries: [SEASON_PATH],
      });
      await waitFor(() =>
        expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  it("click en fila navega al detalle del deportista (tab ai_analysis)", async () => {
    mswServer.use(seasonPanoramaHandler);
    const user = userEvent.setup();
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });

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
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-empty")).toBeInTheDocument(),
    );
  });

  it("muestra error state cuando el endpoint falla", async () => {
    mswServer.use(errorSeasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-error")).toBeInTheDocument(),
    );
  });

  it("año inválido muestra alerta sin disparar fetch", async () => {
    mockYear = "abc";
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: ["/competitions/insights/season/abc"],
    });
    expect(screen.getByText(/Año de temporada inválido/i)).toBeInTheDocument();
    expect(screen.queryByTestId("season-insights-table")).not.toBeInTheDocument();
  });

  it("renderiza las 3 pastillas de vistas hermanas con 'Panorama de temporada' activa", async () => {
    mswServer.use(seasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });

    expect(screen.getByRole("tab", { name: "Válidas" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Sin enlazar" }),
    ).toBeInTheDocument();
    const active = screen.getByRole("tab", { name: "Panorama de temporada" });
    expect(active).toBeInTheDocument();
    expect(active).toHaveAttribute("data-state", "active");
    expect(active).toHaveAttribute("aria-current", "page");
  });
});
