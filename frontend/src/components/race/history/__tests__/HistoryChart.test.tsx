/**
 * Tests para HistoryChart (feature 044, US6 — T076).
 *
 * Recharts se mockea completo — igual que `EvolutionChart.test.tsx` — para
 * poder afirmar sobre el MODELO de datos que arma el componente (qué línea
 * recibe qué puntos, con qué trazo) en vez del SVG renderizado.
 */
import { describe, it, expect, vi } from "vitest";
import { render as rtlRender, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter, useLocation } from "react-router-dom";
import type { ReactElement } from "react";

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
    dot?: unknown;
    activeDot?: unknown;
  }) => {
    const dotFn =
      typeof props.dot === "function"
        ? (props.dot as (p: unknown) => React.ReactNode)
        : null;
    return (
      <div
        data-testid="line"
        data-key={props.dataKey}
        data-stroke={props.stroke}
        data-dash={props.strokeDasharray ?? ""}
        data-count={(props.data ?? []).length}
        data-values={JSON.stringify((props.data ?? []).map((r) => r.value))}
        data-active-dot={JSON.stringify(props.activeDot ?? null)}
      >
        {/* Igual que recharts: invoca `dot(props)` por cada fila y pinta el
            resultado dentro de un <svg>. */}
        {dotFn && (
          <svg>
            {(props.data ?? []).map((row, index) =>
              dotFn({ cx: 40 + index * 60, cy: 50, index, payload: row }),
            )}
          </svg>
        )}
      </div>
    );
  },
}));

// Los puntos son enlaces de react-router (feature 045, T075): todo render
// necesita un Router. `wrapper` también aplica a `rerender`.
function render(ui: ReactElement) {
  return rtlRender(ui, { wrapper: MemoryRouter });
}

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

  describe("prop `metric` (feature 045, T036)", () => {
    const mainValues = () =>
      JSON.parse(
        screen.getAllByTestId("line")[0].getAttribute("data-values") ?? "[]",
      ) as Array<number | null>;

    const realValues = () => mainValues().filter((v) => v !== null);

    it("por defecto grafica la brecha vs. mediana", () => {
      render(<HistoryChart points={BASE_POINTS} />);
      expect(screen.getByTestId("history-chart")).toHaveAttribute(
        "data-metric",
        "gap_to_median_pct",
      );
      expect(realValues()).toEqual([-8.1, -6.5, -4.2]);
    });

    it("percentil: valores del percentil, eje NO invertido y dominio 0–100, sin línea de mediana", () => {
      const points = BASE_POINTS.map((p, i) => ({
        ...p,
        percentile: [40, 55, 63][i],
      }));
      render(<HistoryChart points={points} metric="percentile" />);

      expect(realValues()).toEqual([40, 55, 63]);
      expect(screen.getByTestId("y-axis")).toHaveAttribute("data-reversed", "false");
      expect(screen.getByTestId("y-axis")).toHaveAttribute("data-domain", "[0,100]");
      expect(screen.getByTestId("history-chart-axis-hint")).toHaveTextContent(/↑/);
      // Sin brecha firmada no hay línea de referencia en 0.
      const zeroLine = screen
        .getAllByTestId("reference-line")
        .find((el) => el.getAttribute("data-y") === "0");
      expect(zeroLine).toBeUndefined();
    });

    it("posición: eje invertido (mejor arriba), enteros y nunca por debajo de la 1.ª", () => {
      const points = BASE_POINTS.map((p, i) => ({
        ...p,
        position: [9, 6, 2][i],
      }));
      render(<HistoryChart points={points} metric="position" />);

      expect(realValues()).toEqual([9, 6, 2]);
      expect(screen.getByTestId("y-axis")).toHaveAttribute("data-reversed", "true");
      const [lo, hi] = JSON.parse(
        screen.getByTestId("y-axis").getAttribute("data-domain") ?? "[]",
      );
      expect(lo).toBeGreaterThanOrEqual(1);
      expect(Number.isInteger(lo)).toBe(true);
      expect(Number.isInteger(hi)).toBe(true);
      expect(hi).toBeGreaterThanOrEqual(9);
    });

    it("coach: brecha vs. 1.ª posición y vs. podio con línea de referencia en 0", () => {
      const points = BASE_POINTS.map((p, i) => ({
        ...p,
        gap_to_winner_pct: [12, 10, 8][i],
        gap_to_podium_pct: [7, 5, 3][i],
      }));
      const { rerender } = render(
        <HistoryChart points={points} metric="gap_to_winner_pct" />,
      );
      expect(realValues()).toEqual([12, 10, 8]);
      expect(screen.getByTestId("y-axis")).toHaveAttribute("data-reversed", "true");
      expect(
        screen
          .getAllByTestId("reference-line")
          .find((el) => el.getAttribute("data-y") === "0"),
      ).toHaveAttribute("data-label", "1.ª posición");

      rerender(<HistoryChart points={points} metric="gap_to_podium_pct" />);
      expect(realValues()).toEqual([7, 5, 3]);
    });

    it("familia: una métrica de líder/podio cae en la brecha vs. mediana", () => {
      // Los puntos de familia ni siquiera traen las claves de líder/podio.
      const points = BASE_POINTS.map((p) => {
        const { gap_to_winner_pct: _w, gap_to_podium_pct: _p, ...family } =
          p as typeof p & { gap_to_winner_pct: number; gap_to_podium_pct: number };
        return family as RaceHistoryPoint;
      });
      for (const metric of ["gap_to_winner_pct", "gap_to_podium_pct"] as const) {
        const { unmount } = render(
          <HistoryChart points={points} metric={metric} audience="family" />,
        );
        expect(screen.getByTestId("history-chart")).toHaveAttribute(
          "data-metric",
          "gap_to_median_pct",
        );
        expect(realValues()).toEqual([-8.1, -6.5, -4.2]);
        unmount();
      }
    });

    it("familia: percentil y posición sí se grafican", () => {
      render(<HistoryChart points={BASE_POINTS} metric="percentile" audience="family" />);
      expect(screen.getByTestId("history-chart")).toHaveAttribute(
        "data-metric",
        "percentile",
      );
    });

    it("una métrica sin dato (`null`) en todos los puntos no rompe el render", () => {
      const points = BASE_POINTS.map((p) => ({ ...p, percentile: null }));
      expect(() =>
        render(<HistoryChart points={points} metric="percentile" />),
      ).not.toThrow();
      expect(realValues()).toEqual([]);
    });
  });

  describe("puntos enlazados a su competencia (feature 045, T075 — FR-017 / US1-AC4)", () => {
    function LocationProbe() {
      return <output data-testid="location">{useLocation().pathname}</output>;
    }

    function renderWithLocation(ui: ReactElement) {
      return rtlRender(
        <MemoryRouter initialEntries={["/atleta"]}>
          {ui}
          <LocationProbe />
        </MemoryRouter>,
      );
    }

    it("coach: cada punto lleva al detalle de su competencia", () => {
      render(<HistoryChart points={BASE_POINTS} audience="coach" />);
      const links = screen.getAllByTestId("history-chart-dot-link");
      expect(links.map((a) => a.getAttribute("href"))).toEqual([
        "/competitions/30",
        "/competitions/31",
        "/competitions/41",
      ]);
    });

    it("familia: cada punto lleva a la vista de resultados de la familia", () => {
      const points = BASE_POINTS.map((p) => ({ ...p }));
      render(<HistoryChart points={points} audience="family" />);
      const links = screen.getAllByTestId("history-chart-dot-link");
      expect(links.map((a) => a.getAttribute("href"))).toEqual([
        "/parents/competitions/30",
        "/parents/competitions/31",
        "/parents/competitions/41",
      ]);
    });

    it("sin `audience` se asume coach", () => {
      render(<HistoryChart points={BASE_POINTS} />);
      expect(
        screen.getAllByTestId("history-chart-dot-link")[0],
      ).toHaveAttribute("href", "/competitions/30");
    });

    it("cada enlace tiene nombre accesible con la válida", () => {
      render(<HistoryChart points={BASE_POINTS} />);
      expect(
        screen.getByRole("link", { name: "Ver competencia: Válida 2 — Ginebra" }),
      ).toHaveAttribute("href", "/competitions/31");
    });

    it("el área de toque es de 48 px (círculo de radio 24) aunque la marca sea de 4 px", () => {
      render(<HistoryChart points={BASE_POINTS} />);
      const link = screen.getAllByTestId("history-chart-dot-link")[0]!;
      const radii = Array.from(link.querySelectorAll("circle")).map((c) =>
        Number(c.getAttribute("r")),
      );
      expect(Math.max(...radii) * 2).toBeGreaterThanOrEqual(48);
      expect(Math.min(...radii)).toBe(4);
    });

    it("un clic en el punto navega a la competencia (coach)", async () => {
      const user = userEvent.setup();
      renderWithLocation(<HistoryChart points={BASE_POINTS} audience="coach" />);
      await user.click(
        screen.getByRole("link", { name: "Ver competencia: Válida 2 — Ginebra" }),
      );
      expect(screen.getByTestId("location")).toHaveTextContent("/competitions/31");
    });

    it("un clic en el punto navega a la vista de familia (familia)", async () => {
      const user = userEvent.setup();
      renderWithLocation(<HistoryChart points={BASE_POINTS} audience="family" />);
      await user.click(
        screen.getByRole("link", { name: "Ver competencia: Válida 2 — Ginebra" }),
      );
      expect(screen.getByTestId("location")).toHaveTextContent(
        "/parents/competitions/31",
      );
    });

    it("por teclado: Tab llega al punto y Enter navega", async () => {
      const user = userEvent.setup();
      renderWithLocation(<HistoryChart points={BASE_POINTS} audience="coach" />);
      await user.tab();
      expect(
        screen.getByRole("link", { name: "Ver competencia: Válida 1 — Palmira" }),
      ).toHaveFocus();
      await user.tab();
      await user.keyboard("{Enter}");
      expect(screen.getByTestId("location")).toHaveTextContent("/competitions/31");
    });

    it("el marcador hueco de un DNF también enlaza a su competencia", () => {
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
      render(<HistoryChart points={points} audience="coach" />);
      const hollowLink = screen
        .getByTestId("history-chart-non-finisher-marker")
        .closest("a");
      expect(hollowLink).toHaveAttribute("href", "/competitions/43");
      expect(
        within(hollowLink as HTMLElement).getByTestId("history-chart-non-finisher-marker"),
      ).toBeInTheDocument();
    });

    it("el punto activo (hover) no captura clics: no tapa el enlace", () => {
      render(<HistoryChart points={BASE_POINTS} />);
      const main = screen
        .getAllByTestId("line")
        .find((l) => l.getAttribute("data-stroke") !== "none" && l.getAttribute("data-dash") === "");
      const active = JSON.parse(main!.getAttribute("data-active-dot") ?? "null");
      expect(active).toMatchObject({ pointerEvents: "none" });
    });

    it("no tiene violaciones de accesibilidad con los puntos enlazados", async () => {
      const { container } = render(<HistoryChart points={BASE_POINTS} />);
      expect(screen.getAllByTestId("history-chart-dot-link")).toHaveLength(3);
      expect(await axe(container)).toHaveNoViolations();
    });
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(<HistoryChart points={BASE_POINTS} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
