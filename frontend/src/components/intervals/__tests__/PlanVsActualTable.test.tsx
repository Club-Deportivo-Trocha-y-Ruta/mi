/**
 * Tests para PlanVsActualTable (feature 026, US2 / FR-017):
 *   - Renderiza una fila por bloque planeado con sus columnas formateadas
 *     (duración mm:ss, FC media redondeada, velocidad m/s → km/h con coma
 *     decimal) y el badge de estado (cumplido/fuera de tolerancia/sin dato).
 *   - Bloques `sin_dato` (sin vuelta emparejada) muestran "—" en las columnas
 *     de la vuelta real.
 *   - Vueltas extra se renderizan como filas informativas separadas, nunca
 *     como error.
 *   - Tira de resumen: conteos por estado; el badge de "vueltas extra" solo
 *     aparece si `summary.extra > 0`; toda la tira se omite si no hay `summary`.
 *   - Caption de tolerancia solo aparece si `tolerancePct` está definido.
 *   - Privacidad (Ley 1581, D4): el componente nunca renderiza GPS, polyline,
 *     mapa, cadencia real ni potencia — esas dimensiones no existen en las
 *     props ni en el DOM resultante.
 *   - a11y: jest-axe sin violaciones.
 *
 * Componente presentacional puro — sin data-fetching, sin mocks de red.
 */
import { describe, it, expect } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { PlanVsActualTable } from "../PlanVsActualTable";
import type {
  MatchBlock,
  MatchExtraLap,
  MatchSummary,
} from "@/types/intervals.types";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Fixtures — datos ficticios, nunca datos reales de atletas TyR
// ---------------------------------------------------------------------------

const BLOCK_CUMPLIDO: MatchBlock = {
  flat_index: 0,
  block_type: "warmup",
  repeat_iteration: null,
  planned_duration_s: 300,
  target_zone: "Z1",
  target_cadence_rpm: 70,
  lap_index: 0,
  lap_elapsed_time_s: 312,
  lap_moving_time_s: 300,
  lap_average_heartrate: 128.4,
  lap_average_speed_m_s: 4.1,
  status: "cumplido",
};

const BLOCK_FUERA_TOLERANCIA: MatchBlock = {
  flat_index: 1,
  block_type: "work",
  repeat_iteration: 1,
  planned_duration_s: 120,
  target_zone: "Z3",
  target_cadence_rpm: 85,
  lap_index: 1,
  lap_elapsed_time_s: 200,
  lap_moving_time_s: 195,
  lap_average_heartrate: 165.2,
  lap_average_speed_m_s: 5.5,
  status: "fuera_tolerancia",
};

const BLOCK_SIN_DATO: MatchBlock = {
  flat_index: 2,
  block_type: "cooldown",
  repeat_iteration: null,
  planned_duration_s: 300,
  target_zone: "Z1",
  target_cadence_rpm: 65,
  lap_index: null,
  lap_elapsed_time_s: null,
  lap_moving_time_s: null,
  lap_average_heartrate: null,
  lap_average_speed_m_s: null,
  status: "sin_dato",
};

const EXTRA_LAP: MatchExtraLap = {
  lap_index: 6,
  elapsed_time_s: 45,
  average_heartrate: null,
};

const SUMMARY: MatchSummary = {
  cumplido: 1,
  fuera_tolerancia: 1,
  sin_dato: 1,
  extra: 1,
};

// ---------------------------------------------------------------------------
// Suite: filas de bloque
// ---------------------------------------------------------------------------

describe("PlanVsActualTable — filas de bloque", () => {
  it("renderiza las columnas del encabezado", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} />);

    for (const header of [
      "Bloque",
      "Duración planeada",
      "Zona FC",
      "Cadencia obj.",
      "Vuelta",
      "Duración real",
      "FC media",
      "Vel. media",
      "Estado",
    ]) {
      expect(
        screen.getByRole("columnheader", { name: header }),
      ).toBeInTheDocument();
    }
  });

  it("formatea un bloque cumplido con sus columnas y badge verde", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} />);

    expect(screen.getByText("Calentamiento")).toBeInTheDocument();
    expect(screen.getByText("5:00")).toBeInTheDocument(); // planned_duration_s
    expect(screen.getByText("Z1")).toBeInTheDocument();
    expect(screen.getByText("70 rpm")).toBeInTheDocument();
    expect(screen.getByText("#1")).toBeInTheDocument(); // lap_index 0 → "#1"
    expect(screen.getByText("5:12")).toBeInTheDocument(); // lap_elapsed_time_s
    expect(screen.getByText("128 bpm")).toBeInTheDocument();
    expect(screen.getByText("14,8 km/h")).toBeInTheDocument(); // 4.1 m/s → 14.76 km/h
    expect(screen.getByText("Cumplido")).toBeInTheDocument();
  });

  it("muestra la iteración de repetición entre paréntesis cuando no es null", () => {
    render(<PlanVsActualTable blocks={[BLOCK_FUERA_TOLERANCIA]} />);

    expect(screen.getByText("(rep. 1)")).toBeInTheDocument();
    expect(screen.getByText("Fuera de tolerancia")).toBeInTheDocument();
  });

  it("no muestra la iteración de repetición cuando es null", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} />);

    expect(screen.queryByText(/\(rep\./)).not.toBeInTheDocument();
  });

  it("un bloque sin_dato muestra '—' en las columnas de la vuelta real", () => {
    render(<PlanVsActualTable blocks={[BLOCK_SIN_DATO]} />);

    const row = screen.getByText("Enfriamiento").closest("tr")!;
    const cells = within(row).getAllByRole("cell");
    // Vuelta, Duración real, FC media, Vel. media → todas "—"
    expect(cells.map((c) => c.textContent)).toEqual(
      expect.arrayContaining(["—"]),
    );
    expect(within(row).getByText("Sin dato")).toBeInTheDocument();
  });

  it("renderiza una fila por cada bloque de la lista", () => {
    render(
      <PlanVsActualTable
        blocks={[BLOCK_CUMPLIDO, BLOCK_FUERA_TOLERANCIA, BLOCK_SIN_DATO]}
      />,
    );

    expect(screen.getByText("Calentamiento")).toBeInTheDocument();
    expect(screen.getByText("Trabajo")).toBeInTheDocument();
    expect(screen.getByText("Enfriamiento")).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: vueltas extra
// ---------------------------------------------------------------------------

describe("PlanVsActualTable — vueltas extra", () => {
  it("renderiza una fila informativa por cada vuelta extra, nunca como error", () => {
    render(
      <PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} extraLaps={[EXTRA_LAP]} />,
    );

    const extraRow = screen.getByTestId("plan-vs-actual-extra-lap");
    expect(within(extraRow).getByText("Vuelta extra")).toBeInTheDocument();
    expect(within(extraRow).getByText("#7")).toBeInTheDocument(); // lap_index 6 → "#7"
    expect(within(extraRow).getByText("0:45")).toBeInTheDocument();
    expect(within(extraRow).getByText("Extra")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("sin extraLaps no renderiza ninguna fila de vuelta extra", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} />);

    expect(
      screen.queryByTestId("plan-vs-actual-extra-lap"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: tira de resumen
// ---------------------------------------------------------------------------

describe("PlanVsActualTable — resumen", () => {
  it("renderiza los conteos por estado cuando se provee summary", () => {
    render(<PlanVsActualTable blocks={[]} summary={SUMMARY} />);

    const summaryEl = screen.getByTestId("plan-vs-actual-summary");
    expect(within(summaryEl).getByText("1 cumplidos")).toBeInTheDocument();
    expect(
      within(summaryEl).getByText("1 fuera de tolerancia"),
    ).toBeInTheDocument();
    expect(within(summaryEl).getByText("1 sin dato")).toBeInTheDocument();
    expect(within(summaryEl).getByText("1 vueltas extra")).toBeInTheDocument();
  });

  it("no muestra el badge de vueltas extra cuando extra es 0", () => {
    render(
      <PlanVsActualTable
        blocks={[]}
        summary={{ cumplido: 2, fuera_tolerancia: 0, sin_dato: 0, extra: 0 }}
      />,
    );

    expect(screen.queryByText(/vueltas extra/)).not.toBeInTheDocument();
  });

  it("no renderiza la tira de resumen cuando summary es undefined", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} />);

    expect(
      screen.queryByTestId("plan-vs-actual-summary"),
    ).not.toBeInTheDocument();
  });

  it("no renderiza la tira de resumen cuando summary es null", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} summary={null} />);

    expect(
      screen.queryByTestId("plan-vs-actual-summary"),
    ).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: caption de tolerancia
// ---------------------------------------------------------------------------

describe("PlanVsActualTable — caption de tolerancia", () => {
  it("muestra el caption con el porcentaje de tolerancia cuando se provee", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} tolerancePct={30} />);

    expect(screen.getByText(/±30 %/)).toBeInTheDocument();
  });

  it("no muestra el caption de tolerancia cuando tolerancePct es undefined", () => {
    render(<PlanVsActualTable blocks={[BLOCK_CUMPLIDO]} />);

    expect(screen.queryByText(/dentro del/)).not.toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Suite: privacidad (Ley 1581, D4)
// ---------------------------------------------------------------------------

describe("PlanVsActualTable — privacidad", () => {
  it("nunca renderiza dimensiones de GPS, mapa, cadencia real o potencia", () => {
    const { container } = render(
      <PlanVsActualTable
        blocks={[BLOCK_CUMPLIDO, BLOCK_FUERA_TOLERANCIA]}
        extraLaps={[EXTRA_LAP]}
        summary={SUMMARY}
      />,
    );

    const html = container.innerHTML.toLowerCase();
    for (const forbidden of [
      "latlng",
      "polyline",
      "watt",
      "map",
      "gps",
      "cadencia real",
    ]) {
      expect(html).not.toContain(forbidden);
    }
  });
});

// ---------------------------------------------------------------------------
// Suite: accesibilidad
// ---------------------------------------------------------------------------

describe("PlanVsActualTable — accesibilidad", () => {
  it("no tiene violaciones de a11y con bloques, vueltas extra y resumen", async () => {
    const { container } = render(
      <PlanVsActualTable
        blocks={[BLOCK_CUMPLIDO, BLOCK_FUERA_TOLERANCIA, BLOCK_SIN_DATO]}
        extraLaps={[EXTRA_LAP]}
        summary={SUMMARY}
        tolerancePct={30}
      />,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("no tiene violaciones de a11y con la lista de bloques vacía", async () => {
    const { container } = render(<PlanVsActualTable blocks={[]} />);
    expect(await axe(container)).toHaveNoViolations();
  });
});
