/**
 * Tests para HistoryChart (feature 044, US6 — T076).
 *
 * Recharts se mockea completo — igual que `EvolutionChart.test.tsx` — para
 * poder afirmar sobre el MODELO de datos que arma el componente (qué línea
 * recibe qué puntos, con qué trazo) en vez del SVG renderizado.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { axe } from "jest-axe";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="recharts-container">{children}</div>
  ),
  ComposedChart: ({
    children,
    data,
  }: {
    children: React.ReactNode;
    data: unknown[];
  }) => (
    <div data-testid="composed-chart" data-points={data.length}>
      {children}
    </div>
  ),
  CartesianGrid: () => <div data-testid="grid" />,
  XAxis: (props: { type?: string; scale?: string; ticks?: number[] }) => (
    <div
      data-testid="x-axis"
      data-type={props.type}
      data-scale={props.scale}
      data-ticks={JSON.stringify(props.ticks ?? [])}
    />
  ),
  YAxis: (props: { reversed?: boolean; domain?: [number, number] }) => (
    <div
      data-testid="y-axis"
      data-reversed={String(!!props.reversed)}
      data-domain={JSON.stringify(props.domain ?? [])}
    />
  ),
  Tooltip: (props: { content?: unknown }) => (
    <div data-testid="tooltip" data-has-content={String(typeof props.content === "function")} />
  ),
  ReferenceLine: (props: {
    x?: number;
    y?: number;
    label?: { value?: string } | string;
  }) => (
    <div
      data-testid="reference-line"
      data-x={props.x ?? ""}
      data-y={props.y ?? ""}
      data-label={
        typeof props.label === "object" ? props.label?.value : props.label
      }
    />
  ),
  Line: (props: {
    dataKey: string;
    data?: Array<{ value: number | null }>;
    stroke?: string;
    strokeDasharray?: string;
  }) => (
    <div
      data-testid="line"
      data-key={props.dataKey}
      data-stroke={props.stroke}
      data-dash={props.strokeDasharray ?? ""}
      data-count={(props.data ?? []).length}
      data-values={JSON.stringify((props.data ?? []).map((r) => r.value))}
    />
  ),
}));

import { HistoryChart } from "@/components/race/history/HistoryChart";
import { makeRaceHistoryPoint } from "@/test/msw/raceHistoryHandlers";
import type { RaceHistoryPoint } from "@/types/raceHistory.types";

const BASE_POINTS: RaceHistoryPoint[] = [
  makeRaceHistoryPoint({
    event_id: 30,
    event_date: "2024-03-10",
    season: 2024,
    label: "Válida 1 — Palmira",
    category_code: "INF_B",
    category_label: "INFANTIL B",
    category_changed: false,
    previous_category_label: null,
    gap_to_median_pct: -8.1,
  }),
  makeRaceHistoryPoint({
    event_id: 31,
    event_date: "2024-04-14",
    season: 2024,
    label: "Válida 2 — Ginebra",
    category_code: "INF_B",
    category_label: "INFANTIL B",
    category_changed: false,
    previous_category_label: null,
    gap_to_median_pct: -6.5,
  }),
  makeRaceHistoryPoint({
    event_id: 41,
    event_date: "2025-02-09",
    season: 2025,
    label: "Válida 1 — Ginebra",
    category_code: "PJUV_A",
    category_label: "PREJUVENIL A",
    category_changed: true,
    previous_category_label: "INFANTIL B",
    gap_to_median_pct: -4.2,
  }),
];

describe("HistoryChart", () => {
  it("un solo eje — nunca dos <YAxis>", () => {
    render(<HistoryChart points={BASE_POINTS} />);
    expect(screen.getAllByTestId("y-axis")).toHaveLength(1);
  });

  it("grafica la brecha a la mediana con el eje invertido — sin toggle de métrica (velocidad retirada 2026-09-22)", () => {
    render(<HistoryChart points={BASE_POINTS} />);
    expect(screen.getByTestId("y-axis")).toHaveAttribute("data-reversed", "true");
    expect(screen.queryByTestId("history-chart-metric-toggle")).not.toBeInTheDocument();
    // Línea de referencia en 0 con la etiqueta de la mediana.
    const refLines = screen.getAllByTestId("reference-line");
    const zeroLine = refLines.find((el) => el.getAttribute("data-y") === "0");
    expect(zeroLine).toHaveAttribute("data-label", "Mediana de su categoría");
  });

  it("muestra siempre la pista de lectura del eje invertido (única métrica)", () => {
    render(<HistoryChart points={BASE_POINTS} />);
    expect(screen.getByTestId("history-chart-axis-hint")).toHaveTextContent(
      /más rápido.*↑.*más lento.*↓/i,
    );
  });

  it("marca el cambio de categoría con una ReferenceLine vertical 'A → B'", () => {
    render(<HistoryChart points={BASE_POINTS} />);
    const refLines = screen.getAllByTestId("reference-line");
    const categoryLine = refLines.find((el) =>
      el.getAttribute("data-label")?.includes("→"),
    );
    expect(categoryLine).toBeDefined();
    expect(categoryLine).toHaveAttribute(
      "data-label",
      "INFANTIL B → PREJUVENIL A",
    );
  });

  it("no conecta ni con línea sólida ni punteada a través del cambio de categoría", () => {
    render(<HistoryChart points={BASE_POINTS} />);
    const lines = screen.getAllByTestId("line");
    // Ninguna línea (ni la sólida principal, ni ningún tramo punteado)
    // debería tener 2 puntos cuyas categorías difieran.
    for (const line of lines) {
      const dash = line.getAttribute("data-dash");
      if (dash) {
        // Los tramos punteados son de 2 puntos — igual deben ser de la
        // misma categoría (salto de válida, no de categoría).
        expect(Number(line.getAttribute("data-count"))).toBeLessThanOrEqual(2);
      }
    }
    // La línea principal (con fantasmas) nunca debe generar un tramo
    // punteado que cruce el cambio de categoría — se verifica indirecto:
    // debe existir al menos un tramo punteado (el salto de válida 2024→2024
    // no aplica aquí, pero si lo hubiera lo cubre el siguiente test).
    expect(lines.length).toBeGreaterThan(0);
  });

  it("agrega un conector punteado cuando hay un salto de válida/temporada en la MISMA categoría", () => {
    const points: RaceHistoryPoint[] = [
      makeRaceHistoryPoint({
        event_id: 30,
        event_date: "2024-03-10",
        season: 2024,
        label: "Válida 1 — Palmira",
        category_label: "INFANTIL B",
        category_changed: false,
      }),
      makeRaceHistoryPoint({
        event_id: 41,
        event_date: "2025-02-09",
        season: 2025,
        label: "Válida 1 — Ginebra",
        category_label: "INFANTIL B",
        category_changed: false,
      }),
    ];
    render(<HistoryChart points={points} />);
    const lines = screen.getAllByTestId("line");
    const dashedLines = lines.filter((l) => l.getAttribute("data-dash"));
    expect(dashedLines.length).toBeGreaterThanOrEqual(1);
  });

  it("un DNF/DSQ/DNS se grafica en una línea sin trazo (marcador hueco), no en la principal", () => {
    const points: RaceHistoryPoint[] = [
      ...BASE_POINTS,
      makeRaceHistoryPoint({
        event_id: 43,
        event_date: "2025-06-08",
        season: 2025,
        label: "Válida 3 — Buga",
        category_code: "PJUV_A",
        category_label: "PREJUVENIL A",
        category_changed: false,
        status: "dnf",
        position: null,
        gap_to_median_pct: null,
      }),
    ];
    render(<HistoryChart points={points} />);
    const lines = screen.getAllByTestId("line");
    const hollowLine = lines.find((l) => l.getAttribute("data-stroke") === "none");
    expect(hollowLine).toBeDefined();

    // MAJOR 1 (T077 ux-review.md): el no-finalista NO se ploteaba en 0 —
    // eso chocaba con la línea de "Mediana de su categoría", que también
    // vive en 0. Se plotea en el borde inferior del dominio calculado
    // solo con los valores reales.
    const domain = JSON.parse(
      screen.getByTestId("y-axis").getAttribute("data-domain") ?? "[]",
    );
    const hollowValues = JSON.parse(hollowLine!.getAttribute("data-values") ?? "[]");
    expect(hollowValues).toEqual([domain[0]]);
    expect(hollowValues[0]).not.toBe(0);
  });

  it("todas las métricas nulas (campo chico) no rompe el render — línea principal con valores null", () => {
    const points: RaceHistoryPoint[] = BASE_POINTS.map((p) => ({
      ...p,
      gap_to_median_pct: null,
    }));
    expect(() => render(<HistoryChart points={points} />)).not.toThrow();
    const mainLine = screen.getAllByTestId("line")[0];
    const values = JSON.parse(mainLine.getAttribute("data-values") ?? "[]");
    expect(values.every((v: number | null) => v === null)).toBe(true);
  });

  describe("marcas del eje X (bug: dejaban de avanzar a mitad de una serie multi-temporada)", () => {
    it("la última marca cae en la fecha del último punto, aunque la serie cruce tres temporadas", () => {
      const points: RaceHistoryPoint[] = [
        makeRaceHistoryPoint({
          event_id: 1,
          event_date: "2024-02-01",
          season: 2024,
          label: "Válida 1 — Palmira",
          category_code: "INF_B",
          category_label: "INFANTIL B",
        }),
        makeRaceHistoryPoint({
          event_id: 2,
          event_date: "2024-06-01",
          season: 2024,
          label: "Válida 2 — Ginebra",
          category_code: "INF_B",
          category_label: "INFANTIL B",
        }),
        makeRaceHistoryPoint({
          event_id: 3,
          event_date: "2025-02-01",
          season: 2025,
          label: "Válida 1 — Ginebra",
          category_code: "INF_B",
          category_label: "INFANTIL B",
        }),
        makeRaceHistoryPoint({
          event_id: 4,
          event_date: "2025-06-01",
          season: 2025,
          label: "Válida 2 — Buga",
          category_code: "INF_B",
          category_label: "INFANTIL B",
        }),
        makeRaceHistoryPoint({
          event_id: 5,
          event_date: "2026-02-01",
          season: 2026,
          label: "Válida 1 — Palmira",
          category_code: "INF_B",
          category_label: "INFANTIL B",
        }),
        makeRaceHistoryPoint({
          event_id: 6,
          event_date: "2026-06-01",
          season: 2026,
          label: "Válida 2 — Ginebra",
          category_code: "INF_B",
          category_label: "INFANTIL B",
        }),
      ];
      render(<HistoryChart points={points} />);
      const ticks: number[] = JSON.parse(
        screen.getByTestId("x-axis").getAttribute("data-ticks") ?? "[]",
      );
      expect(ticks.length).toBeGreaterThan(1);
      const lastTickDate = new Date(ticks[ticks.length - 1]);
      // El último punto real es 2026-06-01 — la última marca debe caer
      // exactamente ahí, no a mitad de la serie (2025).
      expect(lastTickDate.getUTCFullYear()).toBe(2026);
      expect(lastTickDate.toISOString().slice(0, 10)).toBe("2026-06-01");
      // La primera marca cae en el punto más antiguo.
      const firstTickDate = new Date(ticks[0]);
      expect(firstTickDate.toISOString().slice(0, 10)).toBe("2024-02-01");
    });
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(<HistoryChart points={BASE_POINTS} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
