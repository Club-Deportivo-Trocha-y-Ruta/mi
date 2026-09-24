/**
 * Tests de UnlinkedSection — «Sin enlazar» de «Cargas e identidades»
 * (feature 045, US3; antes `UnlinkedCompetitorsPage`).
 *
 * Wrapper que monta UnlinkedCompetitorsTab (la herramienta de enlace
 * retroactivo). El comportamiento interno del tab está cubierto por
 * UnlinkedCompetitorsTab.test.tsx; aquí solo se verifica que la sección monta
 * el tab y no deja violaciones de accesibilidad.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { axe } from "jest-axe";

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
import { UnlinkedSection } from "@/components/competitions/imports/UnlinkedSection";

beforeEach(() => {
  vi.clearAllMocks();
});

describe("UnlinkedSection", () => {
  it("monta la herramienta UnlinkedCompetitorsTab", async () => {
    renderWithProviders(<UnlinkedSection />);
    await waitFor(() =>
      expect(
        screen.getByTestId("unlinked-competitors-tab"),
      ).toBeInTheDocument(),
    );
  });

  it("explica para qué sirve la sección", () => {
    renderWithProviders(<UnlinkedSection />);
    expect(
      screen.getByText(
        "Vincula competidores de Copa Valle con los deportistas del club.",
      ),
    ).toBeInTheDocument();
  });

  it("sin violaciones de accesibilidad", async () => {
    const { container } = renderWithProviders(<UnlinkedSection />);
    await screen.findByTestId("unlinked-competitors-tab");
    expect(await axe(container)).toHaveNoViolations();
  });
});
