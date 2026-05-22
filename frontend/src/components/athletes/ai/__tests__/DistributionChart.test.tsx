/**
 * Tests vitest para DistributionChart (FE-3).
 *
 * Cubre:
 *  - Selects season + valida.
 *  - Render chart + reference line cuando hay curve.
 *  - Disclaimer + tabla simple si confidence==="low" (n<5).
 *  - Empty state cuando athlete_time_ms===null.
 *  - Loading/error.
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

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
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
  Area: () => <div data-testid="recharts-area" />,
  CartesianGrid: () => <div data-testid="recharts-grid" />,
  XAxis: () => <div data-testid="recharts-x" />,
  YAxis: () => <div data-testid="recharts-y" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
  ReferenceLine: () => <div data-testid="recharts-ref-line" />,
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div data-testid="recharts-line" />,
}));

import { mswServer } from "@/test/setup";
import {
  lowConfidenceDistributionHandler,
  mockDistribution,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { renderWithProviders } from "@/test/helpers/renderWithProviders";
import { DistributionChart } from "@/components/athletes/ai/DistributionChart";

describe("DistributionChart", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renderiza selectores de season y válida", () => {
    renderWithProviders(<DistributionChart athleteId={42} />);
    expect(screen.getByTestId("distribution-season-select")).toBeInTheDocument();
    expect(screen.getByTestId("distribution-valida-select")).toBeInTheDocument();
  });

  it("renderiza chart + reference line con confidence high (curve presente)", async () => {
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    expect(screen.getByTestId("recharts-ref-line")).toBeInTheDocument();
    // Stats summary muestra Media, Desv, etc.
    expect(screen.getByText(/media/i)).toBeInTheDocument();
    expect(screen.getByText(/desv/i)).toBeInTheDocument();
  });

  it("muestra tabla simple y disclaimer cuando confidence==='low'", async () => {
    mswServer.use(lowConfidenceDistributionHandler);
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByRole("note")).toBeInTheDocument();
    });
    expect(
      screen.getByText(/muestra insuficiente.*n<5/i),
    ).toBeInTheDocument();
    // Tabla con pseudónimos
    expect(screen.getAllByText(/C000\d/).length).toBeGreaterThan(0);
    // El chart NO se renderiza en este caso
    expect(screen.queryByTestId("area-chart")).not.toBeInTheDocument();
  });

  it("empty state cuando el deportista no corrió la válida", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/distribution",
        () =>
          HttpResponse.json(
            mockDistribution({
              athlete_time_ms: null,
              athlete_z_score: null,
              athlete_percentile: null,
            }),
          ),
      ),
    );
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(
        screen.getByText(/el deportista no corrió esta válida/i),
      ).toBeInTheDocument();
    });
  });

  it("muestra error cuando la query falla", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/distribution",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(
        screen.getByText(/no pudimos cargar la distribución/i),
      ).toBeInTheDocument();
    });
  });

  it("cambiar la válida dispara una request con valida_num distinto", async () => {
    const calls: string[] = [];
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/distribution",
        ({ request }) => {
          const url = new URL(request.url);
          calls.push(url.search);
          return HttpResponse.json(mockDistribution());
        },
      ),
    );
    const user = userEvent.setup();
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => expect(screen.getByTestId("area-chart")).toBeInTheDocument());

    const validaSelect = screen.getByTestId(
      "distribution-valida-select",
    ) as HTMLSelectElement;
    await user.selectOptions(validaSelect, "4");

    await waitFor(() => {
      expect(calls.some((s) => s.includes("valida_num=4"))).toBe(true);
    });
  });

  it("destaca al atleta en la tabla low-confidence con is_self=true", async () => {
    mswServer.use(lowConfidenceDistributionHandler);
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByText(/C0002/)).toBeInTheDocument();
    });
    // El row con is_self=true debería mostrar "Tú"
    expect(screen.getByText(/· tú/i)).toBeInTheDocument();
  });

  it("no tiene violaciones a11y (high confidence)", async () => {
    const { container } = renderWithProviders(
      <DistributionChart athleteId={42} />,
    );
    await waitFor(() => expect(screen.getByTestId("area-chart")).toBeInTheDocument());
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones a11y (low confidence / tabla)", async () => {
    mswServer.use(lowConfidenceDistributionHandler);
    const { container } = renderWithProviders(
      <DistributionChart athleteId={42} />,
    );
    await waitFor(() => {
      expect(screen.getByRole("note")).toBeInTheDocument();
    });
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
