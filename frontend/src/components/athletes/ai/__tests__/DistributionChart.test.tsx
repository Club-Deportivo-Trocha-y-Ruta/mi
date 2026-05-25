/**
 * Tests vitest para DistributionChart (FE-3).
 *
 * Cubre:
 *  - Selects season + valida.
 *  - Render chart + reference line cuando hay curve.
 *  - Disclaimer + tabla simple si confidence==="low" (n<5).
 *  - Reference lines de extremos: display_name real (coach) o pseudónimo (parent).
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
  XAxis: ({ domain }: { domain?: unknown }) => (
    <div data-testid="recharts-x" data-domain={JSON.stringify(domain)} />
  ),
  YAxis: () => <div data-testid="recharts-y" />,
  Tooltip: () => <div data-testid="recharts-tooltip" />,
  ReferenceLine: ({ label }: { label?: { value?: string } }) => (
    <div
      data-testid="recharts-ref-line"
      data-label={typeof label === "object" ? label?.value : undefined}
    />
  ),
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: () => <div data-testid="recharts-line" />,
}));

import { mswServer } from "@/test/setup";
import {
  coachHighConfidenceDistributionHandler,
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

  it("renderiza chart + reference lines con confidence high (curve presente)", async () => {
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    // Hay al menos 1 reference line ("Tú" + extremos min/max)
    expect(screen.getAllByTestId("recharts-ref-line").length).toBeGreaterThanOrEqual(1);
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

  it("reference lines muestran TODAS las corredoras con display_name (coach)", async () => {
    mswServer.use(coachHighConfidenceDistributionHandler);
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    const refLines = screen.getAllByTestId("recharts-ref-line");
    const labels = refLines.map((el) => el.getAttribute("data-label")).filter(Boolean);
    // Labels usan SOLO el primer nombre (display compacto).
    // self ("Diego Gómez") NO debe estar — usa la línea "Tú" separada.
    expect(labels).toContain("Luciana");   // mejor
    expect(labels).toContain("Sofía");     // peor
    expect(labels).toContain("Carlos");    // intermedia
    expect(labels).toContain("Andrés");
    expect(labels).toContain("Valentina");
    expect(labels).toContain("Mateo");
    expect(labels).toContain("Isabela");
    // Diego es self → no aparece en RiderReferenceLines (aparece como "P67 · Tú")
    expect(labels).not.toContain("Diego");
  });

  it("reference lines muestran TODOS los pseudónimos cuando display_name es null (parent)", async () => {
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    const refLines = screen.getAllByTestId("recharts-ref-line");
    const labels = refLines.map((el) => el.getAttribute("data-label")).filter(Boolean);
    // Todos los no-self deben tener su pseudónimo. self=C0003 → no aparece aquí.
    expect(labels).toContain("C0001");
    expect(labels).toContain("C0002");
    expect(labels).toContain("C0004");
    expect(labels).toContain("C0005");
    expect(labels).toContain("C0006");
    expect(labels).toContain("C0007");
    expect(labels).toContain("C0008");
    expect(labels).not.toContain("C0003"); // self → fuera
    // No debe haber ningún nombre real
    expect(labels.some((l) => /[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ [A-ZÁÉÍÓÚÑ][a-záéíóúñ]+/.test(l ?? ""))).toBe(false);
  });

  it("el XAxis recibe un dominio más amplio que el rango raw de la curva (padding 8%)", async () => {
    // mockDistribution default: curve xs = [1_700_000, 1_800_000, 1_900_000, 2_000_000, 2_100_000]
    // rango raw = 400_000 ms → pad = 32_000 ms (8%)
    // domain esperado = [1_668_000, 2_132_000]
    renderWithProviders(<DistributionChart athleteId={42} />);
    await waitFor(() => {
      expect(screen.getByTestId("area-chart")).toBeInTheDocument();
    });
    const xAxisEl = screen.getByTestId("recharts-x");
    const raw = xAxisEl.getAttribute("data-domain");
    expect(raw).not.toBeNull();
    const domain = JSON.parse(raw!) as [number, number];
    // El dominio debe ser un array de dos números
    expect(Array.isArray(domain)).toBe(true);
    expect(domain).toHaveLength(2);
    const [lo, hi] = domain;
    // El extremo izquierdo debe ser menor que el mínimo de la curva (1_700_000)
    expect(lo).toBeLessThan(1_700_000);
    // El extremo derecho debe ser mayor que el máximo de la curva (2_100_000)
    expect(hi).toBeGreaterThan(2_100_000);
    // El padding debe ser al menos 1 s (1_000 ms) a cada lado
    expect(1_700_000 - lo).toBeGreaterThanOrEqual(1_000);
    expect(hi - 2_100_000).toBeGreaterThanOrEqual(1_000);
  });
});
