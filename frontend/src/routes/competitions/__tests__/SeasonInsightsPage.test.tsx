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
 *  - Feature 045 (US5/US6): la página es «Temporada» (ruta /competitions/season/:year),
 *    con las secciones «Competencias · Temporada · Cargas e identidades» y el
 *    panel «Análisis pendientes» controlado por `?analisis=por-aprobar|desactualizados`.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import {
  seasonPanoramaHandler,
  seasonPanoramaMultiCupHandler,
  emptySeasonPanoramaHandler,
  errorSeasonPanoramaHandler,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { pendingAnalysesHandlers } from "@/test/msw/racePendingAnalysesHandlers";
import { SeasonInsightsPage } from "@/routes/competitions/SeasonInsightsPage";

// El panel de análisis pendientes consulta con la sesión del coach.
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((selector: (s: unknown) => unknown) =>
    selector({ accessToken: "test-token", user: { id: 1, role: "coach" } }),
  ),
}));

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
const SEASON_PATH = "/competitions/season/2026";

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

  it("click en fila navega a «Carreras › Análisis IA» del deportista", async () => {
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
      "/athletes/144?tab=races&view=analisis",
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
      initialEntries: ["/competitions/season/abc"],
    });
    expect(screen.getByText(/Año de temporada inválido/i)).toBeInTheDocument();
    expect(screen.queryByTestId("season-insights-table")).not.toBeInTheDocument();
  });

  it("titula la página «Temporada» y el retorno dice «Competencias» (nunca «Válidas» como área)", async () => {
    mswServer.use(seasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });

    expect(
      screen.getByRole("heading", { level: 1, name: "Temporada 2026" }),
    ).toBeInTheDocument();
    expect(screen.getByTestId("back-to-insights")).toHaveTextContent("Competencias");
    expect(screen.queryByText("Panorama de temporada 2026")).not.toBeInTheDocument();
  });

  it("renderiza las 3 secciones del área con «Temporada» activa", async () => {
    mswServer.use(seasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });

    expect(screen.getByRole("tab", { name: "Competencias" })).toBeInTheDocument();
    expect(
      screen.getByRole("tab", { name: "Cargas e identidades" }),
    ).toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Válidas" })).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: "Sin enlazar" })).not.toBeInTheDocument();
    const active = screen.getByRole("tab", { name: "Temporada" });
    expect(active).toBeInTheDocument();
    expect(active).toHaveAttribute("data-state", "active");
    expect(active).toHaveAttribute("aria-current", "page");
  });

  it("«Temporada» sigue activa al ver una temporada distinta de la vigente", async () => {
    mockYear = "2025";
    mswServer.use(seasonPanoramaHandler);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: ["/competitions/season/2025"],
    });

    const active = screen.getByRole("tab", { name: "Temporada" });
    expect(active).toHaveAttribute("aria-current", "page");
  });
});

describe("SeasonInsightsPage — análisis pendientes (feature 045, US5)", () => {
  it("sin ?analisis= el panel está cerrado y se ofrece abrirlo (sin pedir nada al backend)", async () => {
    const pendingRequests = vi.fn();
    mswServer.use(
      seasonPanoramaHandler,
      http.get("*/api/race-analysis/pending-analyses", () => {
        pendingRequests();
        return HttpResponse.json([]);
      }),
    );
    renderWithProviders(<SeasonInsightsPage />, { initialEntries: [SEASON_PATH] });

    expect(screen.queryByTestId("pending-analyses-panel")).not.toBeInTheDocument();
    const open = screen.getByTestId("open-pending-analyses");
    expect(open.className).toMatch(/min-h-12/);
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
    );
    expect(pendingRequests).not.toHaveBeenCalled();
  });

  it("?analisis=desactualizados abre el panel con esa lista y la tabla de temporada sigue debajo", async () => {
    mswServer.use(seasonPanoramaHandler, ...pendingAnalysesHandlers);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [`${SEASON_PATH}?analisis=desactualizados`],
    });

    expect(await screen.findByTestId("pending-analyses-list")).toBeInTheDocument();
    expect(screen.getByTestId("pending-mode-desactualizados")).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText("Ana Ficticia")).toBeInTheDocument();
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
    );
  });

  it("?analisis=por-aprobar abre el panel con los borradores por aprobar", async () => {
    mswServer.use(seasonPanoramaHandler, ...pendingAnalysesHandlers);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [`${SEASON_PATH}?analisis=por-aprobar`],
    });

    expect(await screen.findByText("Beto Imaginario")).toBeInTheDocument();
    expect(screen.getByTestId("pending-mode-por-aprobar")).toHaveAttribute("aria-pressed", "true");
  });

  it("un valor desconocido de ?analisis= se ignora: panel cerrado, sin error", async () => {
    mswServer.use(seasonPanoramaHandler, ...pendingAnalysesHandlers);
    renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [`${SEASON_PATH}?analisis=cualquier-cosa`],
    });

    expect(screen.queryByTestId("pending-analyses-panel")).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("abrir el panel, cambiar de modo y ocultarlo mantiene la URL sincronizada", async () => {
    const user = userEvent.setup();
    mswServer.use(seasonPanoramaHandler, ...pendingAnalysesHandlers);
    renderWithProviders(<SeasonInsightsPage />, { initialEntries: [SEASON_PATH] });

    await user.click(screen.getByTestId("open-pending-analyses"));
    expect(await screen.findByTestId("pending-mode-por-aprobar")).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await user.click(screen.getByTestId("pending-mode-desactualizados"));
    expect(screen.getByTestId("pending-mode-desactualizados")).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(await screen.findByText("Ana Ficticia")).toBeInTheDocument();

    await user.click(screen.getByTestId("pending-analyses-close"));
    expect(screen.queryByTestId("pending-analyses-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("open-pending-analyses")).toBeInTheDocument();
  });

  it("a11y: la página con el panel abierto no introduce violaciones", async () => {
    mswServer.use(seasonPanoramaHandler, ...pendingAnalysesHandlers);
    const { container } = renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [`${SEASON_PATH}?analisis=desactualizados`],
    });
    await screen.findByTestId("pending-analyses-list");
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });

  it("a11y: la página con el panel cerrado no introduce violaciones", async () => {
    mswServer.use(seasonPanoramaHandler);
    const { container } = renderWithProviders(<SeasonInsightsPage />, {
      initialEntries: [SEASON_PATH],
    });
    await waitFor(() =>
      expect(screen.getByTestId("season-insights-table")).toBeInTheDocument(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
