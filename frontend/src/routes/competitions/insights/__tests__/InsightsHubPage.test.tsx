/**
 * Tests vitest — InsightsHubPage (índice slim de análisis IA de carreras).
 *
 * Tras eliminar el hub de 5 tabs (RaceAnalysisPage), /competitions/insights
 * monta este índice read-only con 2 accesos: Panorama de temporada y
 * Análisis por válida.
 *
 * Cubre:
 *  - Render del header.
 *  - 2 links/cards con hrefs correctos.
 *  - 0 violaciones a11y (jest-axe).
 */
import { describe, it, expect, afterEach, vi } from "vitest";
import { screen } from "@testing-library/react";
import { axe } from "jest-axe";

import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { InsightsHubPage } from "@/routes/competitions/insights/InsightsHubPage";

describe("InsightsHubPage", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renderiza el header del índice", () => {
    renderWithProviders(<InsightsHubPage />);
    expect(
      screen.getByRole("heading", { name: "Análisis IA carreras" }),
    ).toBeInTheDocument();
  });

  it("muestra el acceso a Panorama de temporada con href al año actual", () => {
    renderWithProviders(<InsightsHubPage />);
    const seasonCard = screen.getByTestId("hub-card-season");
    // El índice apunta a la temporada activa (2026).
    expect(seasonCard).toHaveAttribute(
      "href",
      "/competitions/insights/season/2026",
    );
    expect(seasonCard).toHaveAccessibleName(/panorama de temporada/i);
  });

  it("muestra el acceso a Análisis por válida con href a /competitions/insights/club", () => {
    renderWithProviders(<InsightsHubPage />);
    const clubCard = screen.getByTestId("hub-card-club");
    expect(clubCard).toHaveAttribute("href", "/competitions/insights/club");
    expect(clubCard).toHaveAccessibleName(/análisis por válida/i);
  });

  it("expone exactamente 2 accesos (sin lanzador, sin chat, sin import)", () => {
    renderWithProviders(<InsightsHubPage />);
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    // No debe haber rastros del hub viejo (lanzar análisis / chat / cargar resultados).
    expect(screen.queryByText(/nuevo análisis/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/cargar resultados/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/conversar/i)).not.toBeInTheDocument();
  });

  it("0 violaciones jest-axe", async () => {
    const { container } = renderWithProviders(<InsightsHubPage />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("usa el año activo del reloj (no un 2026 fijo) en el link y el texto de temporada", () => {
    // 2027-06-15T12:00:00Z = 2027-06-15 07:00 en Bogotá (UTC-5): lejos de
    // cualquier cruce de frontera de año, año inequívocamente 2027 (no 2026).
    // Regresión: CURRENT_SEASON estaba hardcodeado a 2026; debe seguir
    // currentSeason() (lib/datetime) y reflejar el reloj real.
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2027-06-15T12:00:00Z"));

    renderWithProviders(<InsightsHubPage />);

    const seasonCard = screen.getByTestId("hub-card-season");
    expect(seasonCard).toHaveAttribute(
      "href",
      "/competitions/insights/season/2027",
    );
    expect(screen.getByText(/Ver temporada 2027/i)).toBeInTheDocument();
    expect(screen.queryByText(/2026/)).not.toBeInTheDocument();
  });
});
