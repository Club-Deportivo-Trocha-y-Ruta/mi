/**
 * Tests vitest — UnlinkedCompetitorsPage (ruta /competitions/unlinked).
 *
 * Wrapper de página que monta UnlinkedCompetitorsTab (la herramienta de enlace
 * retroactivo, reubicada en el módulo Competencias). El comportamiento interno
 * del tab está cubierto por UnlinkedCompetitorsTab.test.tsx; aquí solo
 * verificamos que el wrapper renderiza el header y monta el tab.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";

// La API de competidores se mockea para devolver una lista vacía → el tab
// monta su estado vacío de forma determinista (sin red real).
vi.mock("@/api/raceCompetitors", () => ({
  listUnlinkedCompetitors: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getCompetitorSuggestions: vi.fn(),
  linkCompetitor: vi.fn(),
  unlinkCompetitor: vi.fn(),
}));

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn().mockResolvedValue({ items: [], total: 0 }),
  getAthlete: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { UnlinkedCompetitorsPage } from "@/routes/competitions/UnlinkedCompetitorsPage";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("UnlinkedCompetitorsPage", () => {
  it("renderiza el header de la página", () => {
    renderWithProviders(<UnlinkedCompetitorsPage />);
    expect(
      screen.getByRole("heading", { name: "Competidores sin enlazar" }),
    ).toBeInTheDocument();
  });

  it("monta la herramienta UnlinkedCompetitorsTab", async () => {
    renderWithProviders(<UnlinkedCompetitorsPage />);
    // El tab expone data-testid="unlinked-competitors-tab" una vez resuelto el
    // Suspense + la query inicial.
    await waitFor(() =>
      expect(
        screen.getByTestId("unlinked-competitors-tab"),
      ).toBeInTheDocument(),
    );
  });
});
