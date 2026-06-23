/**
 * Tests para IndividualPanel (US5): puntajes + línea base, nota de
 * no-comparabilidad, flags, y gráfico de evolución (Recharts, lazy) montado.
 * a11y: jest-axe sin violaciones.
 *
 * Recharts se mockea (igual que el resto del proyecto) para que
 * ResponsiveContainer renderice con tamaño fijo en jsdom.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen, within } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";

import { IndividualPanel } from "../IndividualPanel";
import type { AthleteSeries } from "@/types/anxiety.types";

expect.extend(toHaveNoViolations);

vi.mock("recharts", async () => {
  const actual = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 600, height: 200 }}>
        {children}
      </div>
    ),
    LineChart: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="line-chart">{children}</div>
    ),
    Line: () => null,
    XAxis: () => null,
    YAxis: () => null,
    CartesianGrid: () => null,
    Tooltip: () => null,
    Legend: () => null,
    ReferenceLine: () => null,
  };
});

const SERIES: AthleteSeries = {
  athlete_id: 100,
  instrument_type: "csai2r",
  baseline_cognitive: 20,
  baseline_somatic: 22,
  baseline_selfconfidence: 30,
  note: null,
  points: [
    {
      assessment_id: 1,
      scheduled_at: "2026-04-19T12:00:00Z",
      event_id: null,
      cognitive: 20,
      somatic: 22,
      selfconfidence: 30,
      flags: [],
    },
    {
      assessment_id: 2,
      scheduled_at: "2026-05-17T12:00:00Z",
      event_id: 5,
      cognitive: 30,
      somatic: 28,
      selfconfidence: 18,
      flags: ["Atención: conversación individual."],
    },
  ],
};

describe("IndividualPanel", () => {
  it("muestra puntajes del último punto y la línea base", () => {
    render(<IndividualPanel series={SERIES} />);
    // Fila "Cognitiva": último = 30, línea base = 20.
    const row = screen.getByText("Cognitiva").closest("tr");
    expect(row).not.toBeNull();
    const cells = within(row as HTMLElement);
    expect(cells.getByText("30")).toBeInTheDocument();
    expect(cells.getByText("20")).toBeInTheDocument();
  });

  it("renderiza las flags del último punto", () => {
    render(<IndividualPanel series={SERIES} />);
    expect(
      screen.getByText("Atención: conversación individual."),
    ).toBeInTheDocument();
  });

  it("monta el gráfico de evolución (Recharts) lazy-loaded", async () => {
    render(<IndividualPanel series={SERIES} />);
    expect(
      await screen.findByLabelText(
        "Gráfico de evolución de subescalas de ansiedad",
      ),
    ).toBeInTheDocument();
  });

  it("muestra la nota de no-comparabilidad cuando está presente", () => {
    render(<IndividualPanel series={{ ...SERIES, note: "Instrumentos distintos." }} />);
    expect(screen.getByText("Instrumentos distintos.")).toBeInTheDocument();
  });

  it("no tiene violaciones de accesibilidad", async () => {
    const { container } = render(<IndividualPanel series={SERIES} />);
    // Espera a que el chart lazy se monte antes de auditar.
    await screen.findByLabelText(
      "Gráfico de evolución de subescalas de ansiedad",
    );
    expect(await axe(container)).toHaveNoViolations();
  });
});
