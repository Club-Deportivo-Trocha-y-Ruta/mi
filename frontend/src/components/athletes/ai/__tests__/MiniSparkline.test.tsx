/**
 * Tests vitest para MiniSparkline (feature 036, US5).
 *
 * Mockeamos Recharts a un stub liviano — mismo patrón que
 * `EvolutionChart.test.tsx`: `LineChart` refleja su prop `data` en
 * `data-entries` (JSON) para que el test verifique el modelo de datos
 * (incluido el campo `roman` que alimenta el tooltip), no el SVG ni la
 * interacción de hover de Recharts, frágil en jsdom.
 */
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  LineChart: ({
    children,
    data,
  }: {
    children: React.ReactNode;
    data: unknown[];
  }) => (
    <div
      data-testid="line-chart"
      data-points={data.length}
      data-entries={JSON.stringify(data)}
    >
      {children}
    </div>
  ),
  Line: () => <svg data-testid="recharts-line" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
}));

import { describe, it, expect, vi } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";

import { mswServer } from "@/test/setup";
import { cupAndChampionshipConflictHandler } from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { MiniSparkline } from "@/components/athletes/ai/MiniSparkline";

describe("MiniSparkline", () => {
  it("T030 — un campeonato moderno (series_kind='championship', valida_num NO es 99) se etiqueta 'CD' en el tooltip, no el numeral romano de su valida_num de secuencia", async () => {
    // cupAndChampionshipConflictHandler: dos puntos con el MISMO
    // valida_num=1 — uno de copa (series_kind='cup') y uno de campeonato
    // (series_kind='championship'). Antes de este fix, romanForValida()
    // sólo miraba `valida_num === 99` y ambos puntos habrían colapsado al
    // mismo numeral romano "I", perdiendo la distinción "CD" que sí
    // reciben las demás vistas del tab (InsightsTimeline, LaunchAnalysisForm).
    mswServer.use(cupAndChampionshipConflictHandler);
    renderWithProviders(<MiniSparkline athleteId={42} />);

    await waitFor(() => {
      expect(screen.getByTestId("line-chart")).toBeInTheDocument();
    });
    const entries = JSON.parse(
      screen.getByTestId("line-chart").getAttribute("data-entries") ?? "[]",
    ) as Array<{ roman: string; value: number }>;

    expect(entries).toHaveLength(2);
    const cupPoint = entries.find((e) => e.value === 120_000);
    const championshipPoint = entries.find((e) => e.value === 98_000);
    expect(cupPoint?.roman).toBe("I");
    expect(championshipPoint?.roman).toBe("CD");
  });

  it("resumen de temporada (valida_num=0) sigue etiquetándose 'Σ' en el tooltip", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/evolution", () =>
        HttpResponse.json({
          season: 2026,
          metric: "ranking",
          confidence: "high",
          series: [
            {
              valida_num: 1,
              event_id: 91,
              event_date: "2026-01-31",
              value: 3,
              unit: "position",
              series_kind: "cup",
              label: "Válida I — Sevilla",
            },
            {
              valida_num: 0,
              event_id: 92,
              event_date: "2026-02-28",
              value: 2,
              unit: "position",
              series_kind: "cup",
              label: "Resumen de temporada",
            },
          ],
        }),
      ),
    );
    renderWithProviders(<MiniSparkline athleteId={42} />);

    await waitFor(() => {
      expect(screen.getByTestId("line-chart")).toBeInTheDocument();
    });
    const entries = JSON.parse(
      screen.getByTestId("line-chart").getAttribute("data-entries") ?? "[]",
    ) as Array<{ roman: string; value: number }>;
    expect(entries.find((e) => e.value === 2)?.roman).toBe("Σ");
  });
});
