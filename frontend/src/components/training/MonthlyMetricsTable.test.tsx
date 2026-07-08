import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";

import { MonthlyMetricsTable } from "./MonthlyMetricsTable";
import type { MonthlyMetricsSnapshot } from "@/types/trainingSession.types";

function makeMetrics(overrides?: Partial<MonthlyMetricsSnapshot>): MonthlyMetricsSnapshot {
  return {
    total_sessions_planned: 8,
    total_sessions_executed: 6,
    total_sessions_cancelled: 2,
    attendance_by_athlete: {
      "10": {
        athlete_id: 10, count_present: 6, count_absent: 1, count_justified: 0,
        count_late: 1, count_injured: 0, total_sessions: 8, attendance_pct: 75,
      },
      "20": {
        athlete_id: 20, count_present: 4, count_absent: 3, count_justified: 1,
        count_late: 0, count_injured: 1, total_sessions: 8, attendance_pct: 50,
      },
    },
    technical_focus_list: ["Frenada", "Curvas técnicas"],
    technical_focus_counts: { Frenada: 3, "Curvas técnicas": 2 },
    avg_rpe: 6.5,
    avg_rubric_effort: 4.2,
    avg_rubric_attitude: 4.8,
    avg_rubric_technique: 3.9,
    total_minutes_planned: 720,
    total_minutes_executed: 540,
    avg_hours_per_week: 2.1,
    attendance_status_totals: { presente: 30, tarde: 1, justificado: 1, ausente: 4, lesionado: 1 },
    ...overrides,
  };
}

const NAMES = { "10": "Juan Pérez", "20": "Ana Gómez" };

describe("MonthlyMetricsTable", () => {
  it("renderiza todas las secciones", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={NAMES} />);
    expect(screen.getByTestId("monthly-metrics-table")).toBeInTheDocument();
    expect(screen.getByTestId("volume-grid")).toBeInTheDocument();
    expect(screen.getByTestId("attendance-table")).toBeInTheDocument();
    expect(screen.getByTestId("status-totals")).toBeInTheDocument();
    expect(screen.getByTestId("focos-tecnicos")).toBeInTheDocument();
    expect(screen.getByTestId("averages-grid")).toBeInTheDocument();
  });

  it("muestra los KPIs de sesiones (sin planificadas)", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={NAMES} />);
    expect(screen.queryByText("Planificadas")).not.toBeInTheDocument();
    expect(screen.getByText("Ejecutadas")).toBeInTheDocument();
    expect(screen.getByText("Canceladas")).toBeInTheDocument();
  });

  it("la tabla de asistencia muestra nombres reales cuando se proveen", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={NAMES} />);
    expect(screen.getByText("Juan Pérez")).toBeInTheDocument();
    expect(screen.getByText("Ana Gómez")).toBeInTheDocument();
  });

  it("cae a 'Atleta N' cuando no hay nombres (ej. vista sin permisos)", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={{}} />);
    expect(screen.getByText("Atleta 1")).toBeInTheDocument();
    expect(screen.getByText("Atleta 2")).toBeInTheDocument();
  });

  it("ordena la asistencia por porcentaje descendente", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={NAMES} />);
    const rows = screen.getAllByRole("row").slice(1); // sin cabecera
    expect(rows[0]).toHaveTextContent("Juan Pérez"); // 75%
    expect(rows[1]).toHaveTextContent("Ana Gómez"); // 50%
  });

  it("muestra el desglose por estado, con lesionados visibles", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={NAMES} />);
    expect(screen.getByText("Lesion.")).toBeInTheDocument(); // columna
    const totals = screen.getByTestId("status-totals");
    expect(totals).toHaveTextContent("Lesionados: 1");
    expect(totals).toHaveTextContent("Ausencias: 4");
  });

  it("muestra el volumen ejecutado en hh:mm:ss (sin planificado)", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={NAMES} />);
    expect(screen.queryByText("Planificado")).not.toBeInTheDocument();
    expect(screen.getByText("Ejecutado")).toBeInTheDocument();
    expect(screen.getByText("09:00:00")).toBeInTheDocument(); // 540 min ejecutados
    expect(screen.getByText("02:06:00")).toBeInTheDocument(); // 2.1 h/sem
  });

  it("muestra los focos técnicos con su frecuencia", () => {
    render(<MonthlyMetricsTable metrics={makeMetrics()} athleteNames={NAMES} />);
    expect(screen.getByText("Frenada · 3")).toBeInTheDocument();
    expect(screen.getByText("Curvas técnicas · 2")).toBeInTheDocument();
  });

  it("cae a la lista de focos sin conteo si no hay technical_focus_counts", () => {
    render(
      <MonthlyMetricsTable
        metrics={makeMetrics({ technical_focus_counts: undefined })}
        athleteNames={NAMES}
      />,
    );
    expect(screen.getByText("Frenada")).toBeInTheDocument();
    expect(screen.getByText("Curvas técnicas")).toBeInTheDocument();
  });

  it("muestra N/D cuando los promedios de rúbrica son null", () => {
    render(
      <MonthlyMetricsTable
        metrics={makeMetrics({
          avg_rubric_effort: null,
          avg_rubric_attitude: null,
          avg_rubric_technique: null,
        })}
        athleteNames={NAMES}
      />,
    );
    // 3 promedios de rúbrica (RPE omitido); h/sem sigue con valor.
    const ndElements = screen.getAllByText("N/D");
    expect(ndElements.length).toBe(3);
  });

  it("oculta secciones opcionales en reportes antiguos sin los campos SPEC 1", () => {
    render(
      <MonthlyMetricsTable
        metrics={makeMetrics({
          total_minutes_planned: undefined,
          total_minutes_executed: undefined,
          attendance_status_totals: undefined,
        })}
        athleteNames={NAMES}
      />,
    );
    expect(screen.queryByTestId("volume-grid")).not.toBeInTheDocument();
    expect(screen.queryByTestId("status-totals")).not.toBeInTheDocument();
    // La tabla de asistencia sigue presente (dato siempre existió).
    expect(screen.getByTestId("attendance-table")).toBeInTheDocument();
  });

  it("muestra el detalle de sesiones (fecha/hora/foco/lugar/asistencia)", () => {
    render(
      <MonthlyMetricsTable
        metrics={makeMetrics({
          session_detail: [
            {
              session_date: "2026-05-13",
              start_time: "16:30:00",
              technical_focus: "Frenada",
              location: "Pista Panamericana",
              status: "executed",
              present_count: 8,
              attendee_total: 10,
            },
            {
              session_date: "2026-05-20",
              start_time: "07:00:00",
              technical_focus: "Curvas técnicas",
              location: "Bosque Municipal",
              status: "cancelled",
              present_count: 0,
              attendee_total: 10,
            },
          ],
        })}
        athleteNames={NAMES}
      />,
    );
    const table = screen.getByTestId("session-detail-table");
    expect(table).toBeInTheDocument();
    expect(table).toHaveTextContent("13/05/2026");
    expect(table).toHaveTextContent("04:30 p. m.");
    expect(table).toHaveTextContent("Pista Panamericana");
    expect(table).toHaveTextContent("8/10");
    expect(table).toHaveTextContent("Ejecutada");
    expect(table).toHaveTextContent("Cancelada");
  });

  it("muestra 'Pendiente — regenerar informe' cuando session_detail no existe (informe antiguo)", () => {
    render(
      <MonthlyMetricsTable
        metrics={makeMetrics({ session_detail: undefined })}
        athleteNames={NAMES}
      />,
    );
    expect(screen.getByTestId("session-detail-pending")).toHaveTextContent(
      "Pendiente — regenerar informe.",
    );
    expect(screen.queryByTestId("session-detail-table")).not.toBeInTheDocument();
  });

  it("muestra estado vacío cuando session_detail es una lista vacía (período sin sesiones)", () => {
    render(
      <MonthlyMetricsTable
        metrics={makeMetrics({ session_detail: [] })}
        athleteNames={NAMES}
      />,
    );
    expect(screen.getByTestId("session-detail-empty")).toBeInTheDocument();
    expect(screen.queryByTestId("session-detail-table")).not.toBeInTheDocument();
  });
});
