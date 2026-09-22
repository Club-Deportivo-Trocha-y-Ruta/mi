/**
 * Tests para HistoryProgressionCard (feature 044, US6 — T076).
 *
 * `HistoryChart` se mockea como stand-in liviano — igual que
 * `CourseSummary.test.tsx` mockea `CourseMap`/`ElevationProfile` — para no
 * arrastrar recharts real a este archivo (ya cubierto en
 * `HistoryChart.test.tsx`). Este archivo cubre exclusivamente los estados
 * de carga/error/vacío y el bloque "texto primero" (chips, últimos
 * resultados, cambios de categoría, tabla y caveats).
 */
import { createElement, type ReactNode } from "react";
import { describe, it, expect, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe } from "jest-axe";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/race/history/HistoryChart", () => ({
  HistoryChart: ({ points }: { points: unknown[] }) => (
    <div data-testid="mock-history-chart" data-count={points.length} />
  ),
}));

import { mswServer } from "@/test/setup";
import {
  raceHistoryEmptyHandler,
  raceHistoryErrorHandler,
} from "@/test/msw/raceHistoryHandlers";
import { HistoryProgressionCard } from "@/components/race/history/HistoryProgressionCard";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

describe("HistoryProgressionCard", () => {
  it("estado de carga: skeleton con role=status", () => {
    wrap(<HistoryProgressionCard athleteId={99} />);
    expect(screen.getByRole("status", { name: /cargando progresión histórica/i })).toBeInTheDocument();
  });

  it("estado de error: mensaje con role=alert", async () => {
    mswServer.use(raceHistoryErrorHandler);
    wrap(<HistoryProgressionCard athleteId={99} />);
    expect(await screen.findByRole("alert")).toHaveTextContent(
      /no pudimos cargar la progresión histórica/i,
    );
  });

  it("estado vacío: mensaje dedicado, sin chips/tabla/gráfica", async () => {
    mswServer.use(raceHistoryEmptyHandler);
    wrap(<HistoryProgressionCard athleteId={99} />);
    expect(await screen.findByTestId("history-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("season-completion-chips")).not.toBeInTheDocument();
    expect(screen.queryByTestId("history-table")).not.toBeInTheDocument();
    expect(screen.queryByTestId("mock-history-chart")).not.toBeInTheDocument();
  });

  it("con datos: chips, últimos resultados, cambios de categoría, gráfica, tabla y caveats — todo texto-primero antes de la gráfica", async () => {
    wrap(<HistoryProgressionCard athleteId={99} />);

    // El bloque de texto (chips + últimos resultados) no depende de que la
    // gráfica (mockeada, pero simula el chunk lazy) haya terminado de montar.
    expect(await screen.findByTestId("season-completion-chips")).toBeInTheDocument();
    expect(screen.getByTestId("history-latest-three").querySelectorAll("li")).toHaveLength(3);

    expect(screen.getByTestId("history-category-changes")).toHaveTextContent(
      "INFANTIL B → PREJUVENIL A",
    );

    await waitFor(() =>
      expect(screen.getByTestId("mock-history-chart")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("history-table")).toBeInTheDocument();
    expect(screen.getByTestId("history-caveats-note")).toBeInTheDocument();
  });

  it("caveats siempre presente incluso si la API envía una lista con un solo código", async () => {
    mswServer.use(
      http.get("*/api/athletes/:athleteId/race-analysis/history", () =>
        HttpResponse.json({
          points: [
            {
              event_id: 1,
              event_date: "2025-01-01",
              season: 2025,
              label: "Válida 1",
              series_id: 1,
              series_name: "Copa Valle",
              series_kind: "cup",
              category_code: "INF_B",
              category_label: "INFANTIL B",
              category_changed: false,
              previous_category_label: null,
              status: "finished",
              position: 1,
              field_size: 3,
              timed_finishers: 3,
              percentile: null,
              gap_to_median_pct: null,
              gap_to_winner_pct: 0,
              avg_speed_kmh: null,
              points_awarded: 25,
            },
          ],
          seasons: [{ season: 2025, started: 1, finished: 1 }],
          caveats: ["three_rider_categories"],
        }),
      ),
    );
    wrap(<HistoryProgressionCard athleteId={99} />);
    expect(await screen.findByTestId("history-caveats-note")).toHaveTextContent(
      /tres corredores/i,
    );
  });

  it("no tiene violaciones de accesibilidad con datos cargados", async () => {
    const { container } = wrap(<HistoryProgressionCard athleteId={99} />);
    await screen.findByTestId("season-completion-chips");
    await waitFor(() =>
      expect(screen.getByTestId("mock-history-chart")).toBeInTheDocument(),
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
