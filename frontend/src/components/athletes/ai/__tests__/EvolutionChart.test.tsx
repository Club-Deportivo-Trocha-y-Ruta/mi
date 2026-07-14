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
import { Children, cloneElement, isValidElement } from "react";
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
// data-entries: JSON de los datos completos para que T024 inspeccione event_id y label.
// data-key: dataKey de XAxis (T024 verifica que sea "event_id", no "roman").
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
      {/* T032: inyectamos `data` como `chartData` en el <Line> hijo para que
          el mock de Line pueda invocar la prop `dot` (custom render de
          EvolutionChart.tsx) por cada punto — así podemos afirmar que el
          diamante de campeonato (T030) se renderiza en el punto correcto. */}
      {Children.map(children, (child) =>
        isValidElement(child) &&
        (child.props as { dataKey?: string })?.dataKey === "value"
          ? cloneElement(child as React.ReactElement<{ chartData?: unknown[] }>, {
              chartData: data,
            })
          : child,
      )}
    </div>
  ),
  Line: ({
    dot,
    chartData,
  }: {
    dot?: (props: {
      cx: number;
      cy: number;
      index: number;
      payload: unknown;
    }) => React.ReactNode;
    chartData?: unknown[];
  }) => (
    <svg data-testid="recharts-line">
      {(chartData ?? []).map((payload, index) =>
        typeof dot === "function" ? (
          <g key={index}>{dot({ cx: 10 + index * 20, cy: 10, index, payload })}</g>
        ) : null,
      )}
    </svg>
  ),
  // T032: capturamos stroke/strokeDasharray para poder afirmar que la
  // grilla es un hairline sólido — contracts/chart-style.md prohíbe
  // strokeDasharray en <CartesianGrid> (anti-patrón "grilla punteada").
  CartesianGrid: (props: { stroke?: string; strokeDasharray?: string }) => (
    <div
      data-testid="recharts-grid"
      data-stroke={props.stroke}
      data-stroke-dasharray={props.strokeDasharray ?? ""}
    />
  ),
  XAxis: ({ dataKey }: { dataKey?: string }) => (
    <div data-testid="recharts-x" data-key={dataKey} />
  ),
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
  cupAndChampionshipConflictHandler,
  dnfChampionshipHandler,
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
                  series_kind: "cup",
                  label: "Válida I — Sevilla",
                },
                {
                  valida_num: 2,
                  event_id: 92,
                  event_date: "2026-02-28",
                  value: null, // DNF
                  unit: "ms",
                  series_kind: "cup",
                  label: "Válida II — Ginebra",
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

  // ---------------------------------------------------------------------------
  // T024 — TDD-red: campeonato como punto distinto, etiquetado por label
  //
  // ESTADO ESPERADO ANTES DEL FIX (T025–T027):
  //   - Assertion 1 (dos puntos distintos) → FALLA porque chartData filtra por
  //     value!==null y ambos pasan, pero el XAxis usa dataKey="roman" y ambos
  //     tienen roman="I" → se MEZCLAN en la misma categoría del eje.
  //     El test verifica data-entries del LineChart: los dos puntos tienen
  //     event_id distintos (91 y 200), lo que ya pasa. La verificación clave es
  //     que XAxis use dataKey="event_id", no "roman" — eso FALLA en rojo.
  //   - Assertion 2 (etiqueta del campeonato) → FALLA porque roman="I" se
  //     imprime como "Válida I" en el tooltip, no como "Cto. Dep. — Ginebra".
  //   - Assertion 3 (DNF usa label) → FALLA porque la lista DNF renderiza
  //     romanForValida(1)="I", no el label "Cto. Dep. — Ginebra".
  //   - Assertion 4 (a11y) → PASA (sin dependencia del fix).
  //
  // Una vez aplicados T025–T027 todos deben ser GREEN.
  // ---------------------------------------------------------------------------

  describe("T024 — campeonato distinto al eje categorical (TDD-red)", () => {
    it("dos puntos con valida_num=1 pero event_id distintos generan ENTRADAS SEPARADAS en el chart (event_id como clave)", async () => {
      // La serie tiene Copa Válida I (event_id=91) y Campeonato (event_id=200),
      // ambos con valida_num=1. El chart TARGET debe keyear por event_id para
      // NO fusionarlos en la misma categoría.
      mswServer.use(cupAndChampionshipConflictHandler);
      renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });

      // Debe haber exactamente 2 puntos (copa + campeonato).
      const lineChart = screen.getByTestId("line-chart");
      expect(lineChart).toHaveAttribute("data-points", "2");

      // Inspeccionar data-entries: los dos puntos deben tener event_id distintos.
      const rawEntries = lineChart.getAttribute("data-entries");
      expect(rawEntries).not.toBeNull();
      const entries = JSON.parse(rawEntries!) as Array<Record<string, unknown>>;
      const eventIds = entries.map((e) => e["event_id"]);
      expect(eventIds).toContain(91);
      expect(eventIds).toContain(200);

      // CLAVE TDD-red: el XAxis debe usar dataKey="event_id", NO "roman".
      // Actualmente el componente usa dataKey="roman" → este assert FALLA.
      const xAxis = screen.getByTestId("recharts-x");
      expect(xAxis).toHaveAttribute("data-key", "event_id");
    });

    it("el campeonato se etiqueta con su label ('Cto. Dep.') derivado de series_kind, NO de romanForValida", async () => {
      // TARGET: el eje X (o algún texto visible) muestra "Cto. Dep." para el
      // campeonato, en lugar de "I" (que colisionaría con la Copa Válida I).
      // Después del fix T027, el tick del eje usará p.label en lugar de roman.
      mswServer.use(cupAndChampionshipConflictHandler);
      renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);

      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });

      // El componente debe exponer los labels del campeonato en el DOM.
      // T027 los renderizará como ticks del XAxis o como un data-label en el
      // LineChart. Verificamos que la etiqueta del campeonato sea visible.
      // Actualmente romanForValida(1)="I" → "Cto. Dep." nunca aparece → FALLA.
      // T030 añade además un label directo sobre el punto (diamante) — por
      // eso puede haber más de una ocurrencia (leyenda <ol> + marcador).
      expect(screen.getAllByText(/cto\.?\s*dep\./i).length).toBeGreaterThan(0);
    });

    it("la lista DNF ('No finalizó') usa el campo label del punto, no romanForValida(valida_num)", async () => {
      // Escenario: Copa Válida I y Válida II tienen valor, el campeonato (valida_num=1)
      // tiene value=null (DNF). La lista debe mostrar "Cto. Dep. — Ginebra", no "I".
      mswServer.use(dnfChampionshipHandler);
      renderWithProviders(<EvolutionChart athleteId={42} defaultSeason={2026} />);

      await waitFor(() => {
        expect(screen.getByText(/no finalizó/i)).toBeInTheDocument();
      });

      // TARGET: el texto del campeonato DNF debe venir del label, no de roman.
      // Actualmente romanForValida(1)="I" → aparece "I" en lugar de "Cto. Dep." → FALLA.
      const dnfSection = screen.getByText(/no finalizó/i).closest("div");
      expect(dnfSection).toHaveTextContent(/cto\.?\s*dep\./i);

      // Y NO debe mostrar "I" (romano que colisiona con Válida I).
      // Si hubiera solo "I" en la lista DNF, significaría que se usó romanForValida.
      // Nota: "Válida II" (event_id=92) sigue en el chart (value≠null), así que
      // NO aparece en DNF → si vemos "II" en DNF, es otro bug.
      expect(dnfSection?.textContent).not.toMatch(/^.*\bI\b.*$/);
    });

    it("no tiene violaciones a11y con copa+campeonato simultáneos (jest-axe)", async () => {
      // Este test PASA incluso antes del fix — valida que la estructura HTML
      // actual no rompe accesibilidad en el escenario de colisión.
      mswServer.use(cupAndChampionshipConflictHandler);
      const { container } = renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() => {
        expect(screen.getByTestId("line-chart")).toBeInTheDocument();
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("no tiene violaciones a11y con DNF en campeonato (jest-axe)", async () => {
      // Este test PASA incluso antes del fix.
      mswServer.use(dnfChampionshipHandler);
      const { container } = renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() => {
        expect(screen.getByText(/no finalizó/i)).toBeInTheDocument();
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });

  // ---------------------------------------------------------------------------
  // T032 — chart regression contract (contracts/chart-style.md): grid is a
  // solid hairline (no dashing), the championship diamond dot renders iff
  // a point has series_kind==="championship", and the n<3 low-confidence
  // fallback keeps rendering unchanged.
  // ---------------------------------------------------------------------------

  describe("T032 — chart regression contract", () => {
    it("CartesianGrid nunca recibe strokeDasharray (grilla hairline sólida, sin punteado)", async () => {
      renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("line-chart")).toBeInTheDocument(),
      );
      const grid = screen.getByTestId("recharts-grid");
      expect(grid.getAttribute("data-stroke-dasharray")).toBe("");
    });

    it("renderiza el marcador diamante del campeonato cuando un punto tiene series_kind==='championship'", async () => {
      mswServer.use(cupAndChampionshipConflictHandler);
      renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("line-chart")).toBeInTheDocument(),
      );

      // Buscamos SOLO dentro del <svg> mockeado de <Line> — el resto del
      // árbol (iconos lucide del header, p.ej. Calendar/LayoutGrid) también
      // dibuja <rect>/<circle>, así que acotamos el scope a los dots reales.
      const lineSvg = screen.getByTestId("recharts-line");

      // El diamante es un <rect> rotado 45° (no un color nuevo) — exactamente
      // uno, para el único punto series_kind==="championship" del fixture.
      const diamonds = lineSvg.querySelectorAll("rect");
      expect(diamonds).toHaveLength(1);
      expect(diamonds[0].getAttribute("transform")).toContain("rotate(45");

      // Etiqueta directa sobre el punto, ADEMÁS de (no en reemplazo de) la
      // leyenda accesible <ol> — deben coexistir ambas ocurrencias del texto.
      expect(
        screen.getAllByText(/cto\.?\s*dep\./i).length,
      ).toBeGreaterThanOrEqual(2);

      // El punto no-campeonato (copa, event_id=91) sigue como círculo simple.
      expect(lineSvg.querySelectorAll("circle")).toHaveLength(1);
    });

    it("NO renderiza el marcador diamante cuando ningún punto es series_kind==='championship'", async () => {
      // mockEvolution() default: 4 puntos, todos series_kind='cup'.
      renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("line-chart")).toBeInTheDocument(),
      );

      const lineSvg = screen.getByTestId("recharts-line");
      expect(lineSvg.querySelectorAll("rect")).toHaveLength(0);
      expect(screen.queryByText(/cto\.?\s*dep\./i)).not.toBeInTheDocument();
      // Los 4 puntos se marcan como círculo simple en --color-primary.
      expect(lineSvg.querySelectorAll("circle")).toHaveLength(4);
    });

    it("el fallback n<3 (low confidence) se renderiza sin cambios: disclaimer con el texto exacto de siempre", async () => {
      mswServer.use(lowConfidenceEvolutionHandler);
      renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() => {
        expect(screen.getByRole("note")).toBeInTheDocument();
      });
      expect(
        screen.getByText(/muestra insuficiente.*n<3/i),
      ).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------------
  // T033 — el twin de tabla debe ser el equivalente WCAG-limpio de la
  // gráfica por sí mismo (no solo "también presente"): axe corre sobre el
  // contenedor cuando la vista "Tabla" está activa y es la única vista
  // montada (Radix Tabs desmonta el panel inactivo).
  // ---------------------------------------------------------------------------

  describe("T033 — table-view twin es WCAG-limpio por sí mismo (axe)", () => {
    it("la vista Tabla activa no tiene violaciones a11y y reemplaza por completo a la gráfica en el DOM", async () => {
      const user = userEvent.setup();
      const { container } = renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("line-chart")).toBeInTheDocument(),
      );

      await user.click(screen.getByTestId("evolution-tab-table"));

      await waitFor(() => {
        expect(screen.getByTestId("evolution-table")).toBeInTheDocument();
        expect(screen.queryByTestId("line-chart")).not.toBeInTheDocument();
      });

      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("la fila del campeonato en la tabla se marca igual que la leyenda accesible <ol>", async () => {
      mswServer.use(cupAndChampionshipConflictHandler);
      const user = userEvent.setup();
      renderWithProviders(
        <EvolutionChart athleteId={42} defaultSeason={2026} />,
      );
      await waitFor(() =>
        expect(screen.getByTestId("line-chart")).toBeInTheDocument(),
      );

      await user.click(screen.getByTestId("evolution-tab-table"));

      await waitFor(() =>
        expect(screen.getByTestId("evolution-table")).toBeInTheDocument(),
      );
      const champRow = screen
        .getByText("Cto. Dep. — Ginebra")
        .closest("tr");
      expect(champRow).toHaveClass("text-amber-700");
    });
  });
});
