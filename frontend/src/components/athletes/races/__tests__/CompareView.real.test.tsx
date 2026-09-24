/**
 * CompareView con el ComparatorPanel REAL (feature 045, T039).
 *
 * Re-aloja la cobertura del antiguo Sheet del Comparador (BB3) que se perdió
 * al retirar `AthleteAIAnalysisTab`: el comparador ahora va en línea dentro de
 * «Comparar», así que se prueba que
 *   - se monta de una vez (sin botón «Comparar con otro atleta» ni Sheet),
 *   - lee las cifras del servidor (puntos del historial) y compara A → B,
 *   - la vista completa, con datos reales cargados, no tiene violaciones
 *     jest-axe (antes el chequeo cubría el Sheet abierto).
 *
 * `DistributionChart` se mockea (recharts, con su propio spec). El acceso
 * de la familia está cubierto en `CarrerasTab.test.tsx` (sin pestaña
 * «Comparar»; `view=comparar` cae en Progresión).
 */
import { describe, expect, it, vi } from "vitest";
import { screen, within } from "@testing-library/react";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Prueba" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/athletes/ai/DistributionChart", () => ({
  DistributionChart: () => <div data-testid="mock-distribution-chart" />,
}));

import { CompareView } from "@/components/athletes/races/CompareView";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { mockInsight } from "@/test/msw/athleteRaceAnalysisHandlers";
import {
  makeAthleteRaceHistoryRead,
  makeRaceHistoryPoint,
} from "@/test/msw/raceHistoryHandlers";
import { mswServer } from "@/test/setup";
import type { RaceParticipationOption } from "@/types/athleteRaceAnalysis.types";

/** Dos válidas de la misma copa (series 12), event_id = 90 + válida. */
function race(valida: number): RaceParticipationOption {
  return {
    event_id: 90 + valida,
    sequence_number: valida,
    series_kind: "cup",
    event_date: `2026-01-${String(10 + valida).padStart(2, "0")}`,
    event_name: `Copa Valle — Válida ${valida}`,
    location: "Cali",
    label: `Copa Valle · Válida ${valida} — Cali`,
    series_id: 12,
    series_name: "Copa Valle de Ciclomontañismo",
    series_short_name: "Copa Valle",
    series_level: "departmental",
  };
}

function useComparatorData() {
  mswServer.use(
    http.get("*/api/athletes/:athleteId/race-analysis/insights", () => {
      const items = [1, 3].map((v) =>
        mockInsight({
          id: v * 10,
          valida_num: v,
          season: 2026,
          event_id: 90 + v,
          series_id: 12,
          series_name: "Copa Valle de Ciclomontañismo",
          series_short_name: "Copa Valle",
        }),
      );
      return HttpResponse.json({ items, total: items.length, limit: 50, offset: 0 });
    }),
    http.get("*/api/athletes/:athleteId/race-analysis/races", () =>
      HttpResponse.json({ season: 2026, items: [race(1), race(3)] }),
    ),
    http.get("*/api/athletes/:athleteId/anthropometry", () => HttpResponse.json([])),
    http.get("*/api/athletes/:athleteId/race-analysis/history", () =>
      HttpResponse.json(
        makeAthleteRaceHistoryRead({
          points: [
            makeRaceHistoryPoint({
              event_id: 91,
              season: 2026,
              position: 9,
              field_size: 12,
              percentile: 30,
              gap_to_median_pct: 3,
              gap_to_podium_pct: 9,
            }),
            makeRaceHistoryPoint({
              event_id: 93,
              season: 2026,
              position: 5,
              field_size: 12,
              percentile: 70,
              gap_to_median_pct: -2,
              gap_to_podium_pct: 4,
            }),
          ],
        }),
      ),
    ),
  );
}

describe("CompareView — ComparatorPanel real", () => {
  it("monta el comparador en línea, sin Sheet ni botón intermedio", async () => {
    useComparatorData();
    renderWithProviders(<CompareView athleteId={42} />);

    expect(await screen.findByTestId("comparator-panel")).toBeInTheDocument();
    expect(screen.queryByTestId("open-comparator-sheet")).not.toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("compara A → B con las cifras del servidor", async () => {
    useComparatorData();
    renderWithProviders(<CompareView athleteId={42} />);

    const table = await screen.findByTestId("comparator-diff-table");
    const posRow = within(table)
      .getByRole("rowheader", { name: "Posición" })
      .closest("tr") as HTMLElement;
    expect(within(posRow).getByText("P9 de 12")).toBeInTheDocument();
    expect(within(posRow).getByText("P5 de 12")).toBeInTheDocument();
    expect(within(posRow).getByText("−4 puestos")).toBeInTheDocument();
    expect(screen.getByTestId("comparator-improvement-summary")).toHaveTextContent(
      /mejoró 4 de 4 métricas/i,
    );
  });

  it("la vista completa con datos cargados no tiene violaciones jest-axe", async () => {
    useComparatorData();
    const { container } = renderWithProviders(<CompareView athleteId={42} />);
    await screen.findByTestId("comparator-diff-table");

    expect(await axe(container)).toHaveNoViolations();
  });
});
