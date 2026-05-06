import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MonthlyMetricsTable } from "./MonthlyMetricsTable";
import type { MonthlyMetricsSnapshot } from "@/types/trainingSession.types";

function makeMetrics(overrides?: Partial<MonthlyMetricsSnapshot>): MonthlyMetricsSnapshot {
  return {
    total_sessions_planned: 8,
    total_sessions_executed: 6,
    total_sessions_cancelled: 2,
    attendance_stats: [
      { pseudonym: "A1", count_present: 6, count_total: 8, percentage: 75 },
      { pseudonym: "A2", count_present: 4, count_total: 8, percentage: 50 },
    ],
    focos_técnicos: ["Frenada", "Curvas técnicas"],
    avg_rpe: 6.5,
    avg_rubric_effort: 4.2,
    avg_rubric_attitude: 4.8,
    avg_rubric_technique: 3.9,
    ...overrides,
  };
}

describe("MonthlyMetricsTable", () => {
  it("renderiza todas las secciones", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} />);
    expect(screen.getByTestId("monthly-metrics-table")).toBeInTheDocument();
    expect(screen.getByTestId("attendance-table")).toBeInTheDocument();
    expect(screen.getByTestId("focos-tecnicos")).toBeInTheDocument();
    expect(screen.getByTestId("averages-grid")).toBeInTheDocument();
  });

  it("muestra los KPIs correctamente", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} />);
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("Planificadas")).toBeInTheDocument();
    expect(screen.getByText("6")).toBeInTheDocument();
    expect(screen.getByText("Ejecutadas")).toBeInTheDocument();
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("Canceladas")).toBeInTheDocument();
  });

  it("la tabla de asistencia muestra pseudónimos, no nombres reales", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} />);
    expect(screen.getByText("A1")).toBeInTheDocument();
    expect(screen.getByText("A2")).toBeInTheDocument();
  });

  it("ordena la asistencia por porcentaje descendente", () => {
    const metrics = makeMetrics({
      attendance_stats: [
        { pseudonym: "A2", count_present: 4, count_total: 8, percentage: 50 },
        { pseudonym: "A1", count_present: 6, count_total: 8, percentage: 75 },
      ],
    });
    render(<MonthlyMetricsTable metrics={metrics} />);
    const rows = screen.getAllByRole("row").slice(1);
    expect(rows[0]).toHaveTextContent("A1");
    expect(rows[1]).toHaveTextContent("A2");
  });

  it("muestra N/D cuando los promedios son null", () => {
    render(
      <MonthlyMetricsTable
        metrics={makeMetrics({
          avg_rpe: null,
          avg_rubric_effort: null,
          avg_rubric_attitude: null,
          avg_rubric_technique: null,
        })}
      />,
    );
    const ndElements = screen.getAllByText("N/D");
    expect(ndElements.length).toBe(4);
  });

  it("muestra los focos técnicos como chips", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} />);
    expect(screen.getByText("Frenada")).toBeInTheDocument();
    expect(screen.getByText("Curvas técnicas")).toBeInTheDocument();
  });

  it("muestra presencias en formato 'presente / total'", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} />);
    expect(screen.getByText("6 / 8")).toBeInTheDocument();
    expect(screen.getByText("4 / 8")).toBeInTheDocument();
  });
});
