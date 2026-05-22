/**
 * Tests vitest para EvolutionChart (FE-3).
 *
 * Cubre:
 *  - Selects de season y metric cambian la query (interceptamos con
 *    handler MSW custom y verificamos query string).
 *  - Disclaimer cuando confidence==="low".
 *  - Empty state cuando series vacía.
 *  - Loading/error states.
 *
 * Mockeamos componentes Recharts a stubs livianos — recharts en jsdom
 * con ResponsiveContainer puede colgar tests (no hay layout/ResizeObserver
 * real). El test verifica el modelo de datos del chart, no el SVG.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

// Mock Recharts — devolvemos divs simples con info reflejada en data-*
// para que los asserts verifiquen el modelo, no el SVG.
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
    <div data-testid="line-chart" data-points={data.length}>
      {children}
    </div>
  ),
  Line: () => <div data-testid="recharts-line" />,
  CartesianGrid: () => <div data-testid="recharts-grid" />,
  XAxis: () => <div data-testid="recharts-x" />,
  YAxis: () => <div data-testid="recharts-y" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
  ReferenceLine: () => <div data-testid="recharts-ref-line" />,
  Area: () => <div data-testid="recharts-area" />,
  AreaChart: ({
    children,
    data,
  }: {
    children: React.ReactNode;
    data: unknown[];
  }) => (
    <div data-testid="area-chart" data-points={data.length}>
      {children}
    </div>
  ),
}));

import { mswServer } from "@/test/setup";
import {
  emptyEvolutionHandler,
  lowConfidenceEvolutionHandler,
  mockEvolution,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { EvolutionChart } from "@/components/athletes/ai/EvolutionChart";

describe("EvolutionChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza headers + selects de season y metric", async () => {
    renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);
    expect(screen.getByTestId("evolution-season-select")).toBeInTheDocument();
    expect(screen.getByTestId("evolution-metric-select")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByTestId("line-chart")).toBeInTheDocument();
    });
    // 4 puntos del mockEvolution default.
    expect(screen.getByTestId("line-chart")).toHaveAttribute(
      "data-points",
      "4",
    );
  });

  it("disclaimer aparece cuando confidence==='low'", async () => {
    mswServer.use(lowConfidenceEvolutionHandler);
    renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);
    await waitFor(() => {
      expect(screen.getByRole("note")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/muestra insuficiente.*n<3/i),
    ).toBeInTheDocument();
  });

  it("empty state cuando series vacía", async () => {
    mswServer.use(emptyEvolutionHandler);
    renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);
    await waitFor(() => {
      expect(
        screen.getByText(/sin datos para esta temporada/i),
      ).toBeInTheDocument();
    });
    // El chart no se renderiza
    expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();
  });

  it("muestra error cuando la query falla", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/evolution",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);
    await waitFor(() => {
      expect(
        screen.getByText(/no pudimos cargar la evolución/i),
      ).toBeInTheDocument();
    });
  });

  it("cambiar el metric select dispara una nueva request con metric=ranking", async () => {
    const calls: string[] = [];
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/evolution",
        ({ request }) => {
          const url = new URL(request.url);
          calls.push(url.search);
          const metric = url.searchParams.get("metric") ?? "podium_gap_ms";
          return HttpResponse.json(
            mockEvolution({
              metric: metric as "podium_gap_ms" | "ranking" | "time_ms",
            }),
          );
        },
      ),
    );

    const user = userEvent.setup();
    renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);
    await waitFor(() => expect(screen.getByTestId("line-chart")).toBeInTheDocument());

    const select = screen.getByTestId(
      "evolution-metric-select",
    ) as HTMLSelectElement;
    await user.selectOptions(select, "ranking");

    await waitFor(() => {
      expect(calls.some((s) => s.includes("metric=ranking"))).toBe(true);
    });
  });

  it("muestra puntos DNF cuando hay value=null", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/evolution",
        () =>
          HttpResponse.json(
            mockEvolution({
              series: [
                {
                  valida_num: 1,
                  event_id: 91,
                  event_date: "2026-01-31",
                  value: 120_000,
                  unit: "ms",
                },
                {
                  valida_num: 2,
                  event_id: 92,
                  event_date: "2026-02-28",
                  value: null, // DNF
                  unit: "ms",
                },
              ],
            }),
          ),
      ),
    );
    renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);
    await waitFor(() => {
      expect(screen.getByText(/no finalizó/i)).toBeInTheDocument();
    });
  });

  it("no tiene violaciones a11y (estado con datos)", async () => {
    const { container } = renderWithProviders(
      <EvolutionChart athleteId={42} defaultSeason={2026} />,
    );
    await waitFor(() => expect(screen.getByTestId("line-chart")).toBeInTheDocument());
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y (estado vacío)", async () => {
    mswServer.use(emptyEvolutionHandler);
    const { container } = renderWithProviders(
      <EvolutionChart athleteId={42} defaultSeason={2026} />,
    );
    await waitFor(() => {
      expect(
        screen.getByText(/sin datos para esta temporada/i),
      ).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
