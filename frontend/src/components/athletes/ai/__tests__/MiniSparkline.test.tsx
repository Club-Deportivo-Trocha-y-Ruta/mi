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
import {
  championshipOnlyEvolutionHandler,
  cupAndChampionshipConflictHandler,
  multiGroupEvolutionHandler,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { MiniSparkline, romanForValida } from "@/components/athletes/ai/MiniSparkline";

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

  // ---------------------------------------------------------------------------
  // T020 (feature 039) — el sparkline del Panorama solo debe leer la copa
  // (research.md D5/D11): un campeonato es una carrera suelta, no una
  // "válida más" de la tendencia de copa, así que nunca debe mezclarse en
  // esta serie compacta. TDD-red: MiniSparkline.tsx aún no filtra por grupo
  // (T027) — hoy pide la temporada completa sin `series_id` y etiqueta
  // CUALQUIER `series_kind==="championship"` como "CD" sin mirar el nivel,
  // así que ambos tests de abajo deben fallar hasta que T027 aterrice.
  // ---------------------------------------------------------------------------

  it("T020 — con multiGroupEvolutionHandler el sparkline muestra solo los puntos de copa (5) y ningún CD/CN en el tooltip", async () => {
    mswServer.use(multiGroupEvolutionHandler);
    renderWithProviders(<MiniSparkline athleteId={42} />);

    await waitFor(() => {
      expect(screen.getByTestId("line-chart")).toBeInTheDocument();
    });
    const entries = JSON.parse(
      screen.getByTestId("line-chart").getAttribute("data-entries") ?? "[]",
    ) as Array<{ roman: string; value: number }>;

    // El fixture trae 5 válidas de copa + 1 campeonato departamental + 1
    // nacional (7 en total) — el sparkline debe quedarse solo con las 5.
    expect(entries).toHaveLength(5);
    expect(entries.some((e) => e.roman === "CD" || e.roman === "CN")).toBe(
      false,
    );
  });

  it("T020 — con championshipOnlyEvolutionHandler (sin copa en la temporada) muestra el estado vacío 'Sin válidas de copa en esta temporada.'", async () => {
    mswServer.use(championshipOnlyEvolutionHandler);
    renderWithProviders(<MiniSparkline athleteId={42} />);

    await waitFor(() => {
      expect(
        screen.getByText(/sin válidas de copa en esta temporada\.?/i),
      ).toBeInTheDocument();
    });
    expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();
  });

  // ---------------------------------------------------------------------------
  // Fix F-2 (integration-review.md) — `romanForValida` debía leer
  // `series_level` en lugar de devolver "CD" para cualquier campeonato. El
  // camino end-to-end (chart entries) nunca llega a etiquetar un campeonato
  // nacional porque el sparkline solo se activa con `groups.length > 1` +
  // hay copa (T020, arriba) — con 0-1 grupos (único caso donde un punto de
  // campeonato podría llegar al chart) la temporada trae un solo
  // campeonato, así que se prueba la función exportada directamente.
  // ---------------------------------------------------------------------------

  describe("romanForValida (fix F-2)", () => {
    it("un campeonato nacional se etiqueta 'CN', no 'CD'", () => {
      expect(romanForValida(1, true, "national")).toBe("CN");
    });

    it("un campeonato departamental se etiqueta 'CD'", () => {
      expect(romanForValida(1, true, "departmental")).toBe("CD");
    });

    it("sin series_level (fixtures previas a la feature) cae al default 'CD'", () => {
      expect(romanForValida(1, true, undefined)).toBe("CD");
    });

    it("una válida regular ignora series_level y usa el numeral romano", () => {
      expect(romanForValida(3, false, "national")).toBe("III");
    });
  });
});
