/**
 * Tests para ElevationProfile (feature 043 — perfil de circuito, T054/US5).
 *
 * `ElevationProfile` es un componente lazy: un `AreaChart` de Recharts
 * (distancia acumulada en km × elevación en m), serie única en
 * `var(--color-primary)` — mismo token que `EvolutionChart.tsx` y
 * `CourseMap.tsx`. El componente decima internamente a ≤200 muestras
 * (bucketing por distancia acumulada, no por índice — los puntos de un GPX
 * no están espaciados uniformemente), pero min/max del `aria-label` se
 * calculan SIEMPRE sobre el set COMPLETO de elevaciones (nunca sobre los
 * datos ya decimados que ve el chart) — de lo contrario un pico/valle real
 * podría perderse si cae en un bucket descartado.
 *
 * Mockeamos "recharts" con stubs livianos (mismo patrón que
 * `EvolutionChart.test.tsx`/`PercentileChart.test.tsx` — jsdom no tiene
 * layout real ni ResizeObserver, así que ResponsiveContainer/AreaChart se
 * reemplazan por <div> que reflejan sus props en atributos `data-*`).
 * Solo nos interesa que el componente no explote con >200 puntos y que
 * `data` llegue con ≤200 entradas — el resto (min/max/aria-label) surge
 * del propio wrapper `role="img"`, no de los internals de Recharts.
 *
 * `elevationGainM` es un prop que se muestra verbatim (viene ya calculado
 * en el backend, `VariantRead.elevation_gain_m`) — este componente NO debe
 * recalcularlo.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";

vi.mock("recharts", () => ({
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="elevation-responsive">{children}</div>
  ),
  AreaChart: ({
    children,
    data,
  }: {
    children: React.ReactNode;
    data: unknown[];
  }) => (
    <div data-testid="elevation-area-chart" data-points={data.length}>
      {children}
    </div>
  ),
  Area: () => <div data-testid="elevation-area" />,
  CartesianGrid: () => <div data-testid="elevation-grid" />,
  XAxis: () => <div data-testid="elevation-x" />,
  YAxis: ({ domain }: { domain?: unknown }) => (
    <div data-testid="elevation-y" data-domain={JSON.stringify(domain)} />
  ),
  Tooltip: () => <div data-testid="elevation-tooltip" />,
}));

import { ElevationProfile } from "@/components/race/course/ElevationProfile";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

/** 5 puntos — min=950 (índice 1), max=1020 (índice 2), valores enteros para
 * que la redondeada a entero del aria-label no introduzca ambigüedad. */
const SMALL_GEOMETRY: Array<[number, number, number | null]> = [
  [3.45, -76.53, 1000],
  [3.4505, -76.5305, 950],
  [3.451, -76.531, 1020],
  [3.4515, -76.5315, 980],
  [3.452, -76.532, 990],
];

/** 250 puntos espaciados uniformemente (~misma distancia entre consecutivos)
 * con una banda estrecha 1000-1012 salvo dos extremos deliberados en índices
 * "no redondos" (137 y 210) — 700 (mínimo global) y 1300 (máximo global).
 * Cualquier estrategia de decimación por índice (cada N-ésimo punto) muy
 * probablemente descarta esos dos índices; el aria-label solo es correcto
 * si min/max se calculan sobre el set COMPLETO, no sobre `data` del chart. */
function buildLargeGeometry(): Array<[number, number, number | null]> {
  const points: Array<[number, number, number | null]> = [];
  for (let i = 0; i < 250; i++) {
    let ele = 1000 + (i % 7) * 2; // banda 1000-1012
    if (i === 137) ele = 700; // mínimo global
    if (i === 210) ele = 1300; // máximo global
    points.push([3.45 + i * 0.0001, -76.53 - i * 0.0001, ele]);
  }
  return points;
}

const LARGE_GEOMETRY = buildLargeGeometry();

// ---------------------------------------------------------------------------
// Eje Y ajustado al rango real
// ---------------------------------------------------------------------------

describe("ElevationProfile — eje Y", () => {
  it("el dominio parte del rango real con margen (no desde 0 m), para que el desnivel sea visible", () => {
    // min=950, max=1020 → margen max(10, 70·0.15)=10.5 → [930, 1040].
    render(<ElevationProfile geometry={SMALL_GEOMETRY} elevationGainM={70} />);
    expect(screen.getByTestId("elevation-y")).toHaveAttribute(
      "data-domain",
      "[930,1040]",
    );
  });
});

// ---------------------------------------------------------------------------
// aria-label — min/max (enteros) + elevationGainM verbatim
// ---------------------------------------------------------------------------

describe("ElevationProfile — aria-label", () => {
  it('role="img" con aria-label "Perfil de altimetría: de {min} a {max} m, {elevationGainM} m de desnivel positivo"', () => {
    render(
      <ElevationProfile geometry={SMALL_GEOMETRY} elevationGainM={70} />,
    );
    const img = screen.getByRole("img");
    expect(img).toHaveAttribute(
      "aria-label",
      "Perfil de altimetría: de 950 a 1020 m, 70 m de desnivel positivo",
    );
  });

  it("elevationGainM se muestra verbatim (no se recalcula a partir de la geometría)", () => {
    // elevationGainM=999 es deliberadamente distinto de cualquier figura
    // derivable de SMALL_GEOMETRY (min=950, max=1020, rango=70) — si el
    // componente lo recalculara en vez de usar el prop, este valor no
    // aparecería en el aria-label.
    render(
      <ElevationProfile geometry={SMALL_GEOMETRY} elevationGainM={999} />,
    );
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Perfil de altimetría: de 950 a 1020 m, 999 m de desnivel positivo",
    );
  });

  it("min/max son enteros (sin decimales) en el aria-label, incluso con elevaciones fraccionarias en la geometría", () => {
    const geometry: Array<[number, number, number | null]> = [
      [3.45, -76.53, 950.6],
      [3.451, -76.531, 1019.4],
    ];
    render(<ElevationProfile geometry={geometry} elevationGainM={69} />);
    const label = screen.getByRole("img").getAttribute("aria-label") ?? "";
    // Cualquiera sea el método de redondeo, el aria-label nunca lleva
    // decimales — ni "950.6" ni "1019.4" literalmente.
    expect(label).not.toMatch(/\.\d/);
    expect(label).not.toContain("950.6");
    expect(label).not.toContain("1019.4");
  });
});

// ---------------------------------------------------------------------------
// Decimación — >200 puntos no debe crashear y el aria-label sigue reflejando
// el set COMPLETO (no el decimado).
// ---------------------------------------------------------------------------

describe("ElevationProfile — decimación (>200 puntos)", () => {
  it("no crashea con 250 puntos y decima a ≤200 muestras para el chart", () => {
    expect(() =>
      render(
        <ElevationProfile geometry={LARGE_GEOMETRY} elevationGainM={600} />,
      ),
    ).not.toThrow();

    const chart = screen.getByTestId("elevation-area-chart");
    const points = Number(chart.getAttribute("data-points"));
    expect(points).toBeGreaterThan(0);
    expect(points).toBeLessThanOrEqual(200);
  });

  it("el aria-label refleja el mínimo/máximo del set COMPLETO (700/1300), no solo lo que sobrevive a la decimación", () => {
    render(
      <ElevationProfile geometry={LARGE_GEOMETRY} elevationGainM={600} />,
    );
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Perfil de altimetría: de 700 a 1300 m, 600 m de desnivel positivo",
    );
  });
});

// ---------------------------------------------------------------------------
// Elevaciones null — tratamiento defensivo (no se diseña un empty-state
// aquí; eso vive en CourseSummary cuando has_elevation===false).
// ---------------------------------------------------------------------------

describe("ElevationProfile — elevaciones null (defensivo)", () => {
  it("no crashea cuando algunos puntos (no todos) tienen elevación null", () => {
    const geometry: Array<[number, number, number | null]> = [
      [3.45, -76.53, 1000],
      [3.451, -76.531, null],
      [3.452, -76.532, 980],
      [3.453, -76.533, null],
      [3.454, -76.534, 1010],
    ];
    expect(() =>
      render(<ElevationProfile geometry={geometry} elevationGainM={30} />),
    ).not.toThrow();
    // min/max solo sobre los valores no nulos (980/1010).
    expect(screen.getByRole("img")).toHaveAttribute(
      "aria-label",
      "Perfil de altimetría: de 980 a 1010 m, 30 m de desnivel positivo",
    );
  });
});

// ---------------------------------------------------------------------------
// Altura compacta en mobile (160px)
// ---------------------------------------------------------------------------

describe("ElevationProfile — layout", () => {
  it("altura fija de 160px en mobile (h-40)", () => {
    render(
      <ElevationProfile geometry={SMALL_GEOMETRY} elevationGainM={70} />,
    );
    expect(screen.getByRole("img").className).toMatch(/\bh-40\b/);
  });
});
