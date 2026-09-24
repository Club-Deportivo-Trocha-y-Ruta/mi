/**
 * AnalysisView en audiencia familiar — privacidad (feature 045, US4 / T042).
 *
 * Re-alojada desde `AthleteAIAnalysisTab.parent.test.tsx`. Las aserciones de
 * estructura (sin lanzador/chat/resumen/casillas/barra de boletín, etiqueta de
 * IA revisada por el entrenador) viven en `AnalysisView.test.tsx`; acá quedan
 * las de privacidad transversal (Ley 1581) que corren con `PanoramaView` REAL:
 *
 *  - el árbol renderizado nunca menciona metadatos de IA (modelo, prompt,
 *    tokens, costo, confianza, telemetría) ni montos en USD;
 *  - nunca se pinta el nombre de un competidor aunque un backend defectuoso lo
 *    enviara en la serie de evolución (`data-model.md` §ChampionshipReading:
 *    la serie "never includes names, bibs or competitor ids");
 *  - sin acceso a la vista «Comparar» ni a su Sheet (ahora en `CompareView`,
 *    coach-only: la vista no expone ningún enlace hacia ella).
 *
 * Se mockean InsightsTimeline y LaunchAnalysisForm (ajenos a esta prueba).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 20, role: "parent", first_name: "Padre", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/athletes/ai/InsightsTimeline", () => ({
  InsightsTimeline: ({ mode }: { mode: string }) => (
    <div data-testid="mock-insights-timeline">timeline-{mode}</div>
  ),
}));
vi.mock("@/components/athletes/ai/LaunchAnalysisForm", () => ({
  LaunchAnalysisForm: () => <div data-testid="mock-launch-form">launch</div>,
}));

import { mswServer } from "@/test/setup";
import { mockEvolution } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { AnalysisView } from "@/components/athletes/races/AnalysisView";
import type { AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

const athlete: AthleteOut = {
  id: 42,
  user_id: 100,
  first_name: "Atleta",
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

describe("AnalysisView — audiencia familiar (privacidad)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("nunca expone datos operativos sensibles (modelo, prompt, tokens, costo, confianza, telemetría)", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="family" />);
    await screen.findByTestId("mock-insights-timeline");

    const tree = screen.getByTestId("analysis-view").textContent ?? "";
    const sensitivePatterns: RegExp[] = [
      /confianza/i,
      /confidence/i,
      /\$\d/,
      /tokens?/i,
      /\bprompt\b/i,
      /\bmodel\b/i,
      /gemini/i,
      /flash-lite/i,
      /telemetr/i,
      /\bcost(o|s)?\b/i,
    ];
    sensitivePatterns.forEach((p) => {
      expect(tree).not.toMatch(p);
    });
  });

  it("no tiene acceso a Comparar/Distribución: ni botón del Sheet ni sub-tab", async () => {
    renderWithProviders(<AnalysisView athlete={athlete} audience="family" />);
    await screen.findByTestId("mock-insights-timeline");

    expect(screen.queryByTestId("open-comparator-sheet")).not.toBeInTheDocument();
    expect(screen.queryByTestId("ai-subtab-distribution")).not.toBeInTheDocument();
    expect(screen.queryByRole("tab", { name: /comparar/i })).not.toBeInTheDocument();
  });

  it("nunca expone el nombre de un competidor en el widget de evolución", async () => {
    // `MiniSparkline` (dentro de PanoramaView, REAL en este archivo) solo lee
    // `roman` y `value` de cada punto, así que un campo extra con datos de un
    // tercero no tiene por dónde filtrarse al DOM. Simulamos un backend que
    // rompiera la invariante (mismo espíritu que el fixture
    // `display_name="Winner Real"` de
    // tests/routers/test_athlete_race_analysis_privacy.py) y confirmamos que el
    // cliente nunca lo pinta.
    const LEAKED_COMPETITOR_NAME = "Camila Rodríguez Rival Ficticia";
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/evolution", () => {
        const base = mockEvolution();
        const series = base.series.map((point, idx) =>
          idx === 0
            ? { ...point, competitor_display_name: LEAKED_COMPETITOR_NAME }
            : point,
        );
        return HttpResponse.json({ ...base, series });
      }),
    );

    renderWithProviders(<AnalysisView athlete={athlete} audience="family" />);
    await waitFor(() => {
      expect(screen.getByTestId("mini-evolution-sparkline")).toBeInTheDocument();
    });

    const tree = screen.getByTestId("analysis-view").textContent ?? "";
    expect(tree).not.toContain(LEAKED_COMPETITOR_NAME);
    expect(tree).not.toContain("Rodríguez");
  });
});
