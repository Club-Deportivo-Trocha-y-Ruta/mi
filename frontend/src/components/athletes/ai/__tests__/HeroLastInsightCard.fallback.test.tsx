/**
 * HeroLastInsightCard — fila fallback (US4, feature 036).
 *
 * Antes de este fix, un insight con `is_fallback=true` (placeholder de
 * falla de `deterministic_fallback`, ver `InsightsTimeline.fallback.test.tsx`)
 * seguía mostrando el toggle "Agregar al boletín" sin ningún marcado: el
 * guard real de 422 vive en el backend, pero el coach no veía ninguna señal
 * en este card — el botón parecía funcionar y sólo la sticky bar fallaba al
 * enviar. Este archivo cubre el mismo contrato que ya tenía
 * `InsightsTimeline.tsx` (badge visible, botón de boletín suprimido) para
 * el card "Panorama", que muestra el mismo insight por un camino distinto.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
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

import { mswServer } from "@/test/setup";
import {
  fallbackInsightListHandler,
  mockInsight,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { http, HttpResponse } from "msw";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { HeroLastInsightCard } from "@/components/athletes/ai/HeroLastInsightCard";
import type { AthleteInsightListResponse } from "@/types/athleteRaceAnalysis.types";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Juan Pérez",
  last_name: "Ficticio",
  birth_date: "2012-01-15",
  sex: Sex.M,
  club_join_date: "2024-01-01",
  years_in_club: 2,
  age_decimal: 14.3,
  category: "Sub-15",
  club_id: 1,
  created_at: "2024-01-01T00:00:00Z",
};

describe("HeroLastInsightCard — fila fallback (US4, feature 036)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("marca el insight fallback con badge y NO ofrece 'Agregar al boletín' (coach)", async () => {
    mswServer.use(fallbackInsightListHandler);
    renderWithProviders(
      <HeroLastInsightCard
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("hero-insight-fallback-badge"),
    ).toHaveTextContent(/análisis no disponible/i);
    expect(
      screen.queryByTestId("hero-btn-add-newsletter"),
    ).not.toBeInTheDocument();
  });

  it("un insight real (no fallback) conserva el botón 'Agregar al boletín' (regresión)", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        () => {
          const response: AthleteInsightListResponse = {
            items: [mockInsight()],
            total: 1,
            limit: 50,
            offset: 0,
          };
          return HttpResponse.json(response);
        },
      ),
    );
    renderWithProviders(
      <HeroLastInsightCard
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    expect(
      screen.queryByTestId("hero-insight-fallback-badge"),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("hero-btn-add-newsletter")).toBeInTheDocument();
  });

  it("parent tampoco ve el botón de boletín en una fila fallback, y sí ve el marcado", async () => {
    mswServer.use(fallbackInsightListHandler);
    renderWithProviders(
      <HeroLastInsightCard
        athlete={athlete}
        mode="parent"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    expect(
      screen.getByTestId("hero-insight-fallback-badge"),
    ).toBeInTheDocument();
    expect(
      screen.queryByTestId("hero-btn-add-newsletter"),
    ).not.toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad con un insight fallback", async () => {
    mswServer.use(fallbackInsightListHandler);
    const { container } = renderWithProviders(
      <HeroLastInsightCard
        athlete={athlete}
        mode="coach"
        onOpenDetail={vi.fn()}
        onAddToNewsletter={vi.fn()}
      />,
    );
    await waitFor(() => {
      expect(screen.getByTestId("hero-btn-reread")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
