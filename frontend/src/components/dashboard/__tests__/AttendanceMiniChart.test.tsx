/**
 * Tests de AttendanceMiniChart — tarjeta "Asistencia" del Inicio del coach
 * (feature 035, fila C del mockup `Main.dc.html`).
 *
 * Cubre:
 *  - el cálculo del porcentaje ((presentes + tardes) / total, redondeado),
 *  - la selección de las últimas 4 sesiones ejecutadas CON asistencia
 *    registrada, en orden cronológico,
 *  - el equivalente textual `sr-only` (el gráfico va `aria-hidden`),
 *  - los estados vacío / error real (misma línea neutra) y cold start
 *    (esqueleto, nunca tono de error),
 *  - la ventana compartida con `WeekStrip` (misma queryKey ⇒ sin request
 *    adicional).
 *
 * "Hoy" se fija en 2026-08-27T20:00:00Z == jueves 27 de agosto, 15:00 en
 * America/Bogotá (UTC-5, sin DST).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";

import type {
  AttendanceSummaryCounts,
  TrainingSession,
} from "@/types/trainingSession.types";

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
}));

import { useTrainingSessions } from "@/api/trainingSessions";

import { AttendanceMiniChart } from "../AttendanceMiniChart";
import { executedSessionsFilters } from "../WeekStrip";

const mockUseTrainingSessions = vi.mocked(useTrainingSessions);

type QueryResult = ReturnType<typeof useTrainingSessions>;

function makeSummary(overrides: Partial<AttendanceSummaryCounts> = {}): AttendanceSummaryCounts {
  return {
    total: 10,
    presentes: 8,
    ausentes: 2,
    justificados: 0,
    tardes: 0,
    lesionados: 0,
    ...overrides,
  };
}

function makeExecuted(overrides: Partial<TrainingSession> = {}): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 1,
    status: "executed",
    scheduled_date: "2026-08-25",
    scheduled_start_time: "16:00:00",
    duration_min: 90,
    location: "Parque de la Salud",
    technical_focus: "Resistencia Z2",
    description: "",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    attendance_summary: makeSummary(),
    ...overrides,
  };
}

function stubQuery(overrides: Partial<{ isLoading: boolean; isError: boolean; error: unknown; data: TrainingSession[] }>) {
  mockUseTrainingSessions.mockReturnValue({
    isLoading: false,
    isError: false,
    data: [],
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as QueryResult);
}

describe("AttendanceMiniChart", () => {
  beforeEach(() => {
    mockUseTrainingSessions.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-27T20:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("consume la MISMA ventana de sesiones ejecutadas que WeekStrip (cache compartido)", () => {
    stubQuery({ data: [] });

    render(<AttendanceMiniChart />);

    expect(mockUseTrainingSessions).toHaveBeenCalledWith(executedSessionsFilters());
  });

  it("calcula el porcentaje contando presentes + tardes sobre el total", () => {
    stubQuery({
      data: [
        makeExecuted({
          id: 1,
          scheduled_date: "2026-08-25",
          attendance_summary: makeSummary({ total: 12, presentes: 7, tardes: 2, ausentes: 3 }),
        }),
      ],
    });

    render(<AttendanceMiniChart />);

    // (7 + 2) / 12 = 75 % — sin las tardes daría 58 %.
    expect(screen.getByText("75 %")).toBeInTheDocument();
    expect(screen.queryByText("58 %")).not.toBeInTheDocument();
  });

  it("muestra sólo las últimas 4 sesiones con asistencia, en orden cronológico", () => {
    stubQuery({
      data: [
        makeExecuted({
          id: 1,
          scheduled_date: "2026-07-01",
          attendance_summary: makeSummary({ total: 10, presentes: 1 }),
        }),
        makeExecuted({
          id: 2,
          scheduled_date: "2026-08-18",
          attendance_summary: makeSummary({ total: 10, presentes: 7, tardes: 1 }),
        }),
        makeExecuted({
          id: 3,
          scheduled_date: "2026-08-20",
          attendance_summary: makeSummary({ total: 10, presentes: 9 }),
        }),
        makeExecuted({
          id: 4,
          scheduled_date: "2026-08-22",
          attendance_summary: makeSummary({ total: 10, presentes: 10 }),
        }),
        makeExecuted({
          id: 5,
          scheduled_date: "2026-08-25",
          attendance_summary: makeSummary({ total: 10, presentes: 6, tardes: 2 }),
        }),
        // Sin asistencia registrada: no participa del gráfico.
        makeExecuted({
          id: 6,
          scheduled_date: "2026-08-26",
          attendance_summary: makeSummary({ total: 0, presentes: 0 }),
        }),
        // Sin bloque de asistencia del todo.
        makeExecuted({ id: 7, scheduled_date: "2026-08-26", attendance_summary: null }),
      ],
    });

    render(<AttendanceMiniChart />);

    // La más antigua (1 de julio, 10 %) queda fuera del tope de 4.
    expect(screen.queryByText("10 %")).not.toBeInTheDocument();
    // 18 ago y 25 ago comparten valor (80 %): dos barras, no una.
    expect(screen.getAllByText("80 %")).toHaveLength(2);
    expect(screen.getByText("90 %")).toBeInTheDocument();
    expect(screen.getByText("100 %")).toBeInTheDocument();

    const summary = screen.getByText(/Asistencia por sesión/);
    expect(summary).toHaveTextContent(/18.*ago.*80 %.*20.*ago.*90 %.*22.*ago.*100 %.*25.*ago.*80 %/);
    expect(summary.className).toMatch(/sr-only/);
  });

  it("sin sesiones con asistencia registrada, muestra la línea neutra (no un gráfico vacío)", () => {
    stubQuery({ data: [] });

    render(<AttendanceMiniChart />);

    expect(screen.getByRole("heading", { name: "Asistencia" })).toBeInTheDocument();
    expect(screen.getByText("Últimas 4 sesiones")).toBeInTheDocument();
    expect(
      screen.getByText("Aún no hay sesiones con asistencia registrada"),
    ).toBeInTheDocument();
  });

  it("error real: línea neutra de 'no se pudo cargar', nunca la copy de vacío ni un tono de error", () => {
    stubQuery({ isError: true, error: new Error("Error de validación"), data: undefined });

    render(<AttendanceMiniChart />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("No se pudo cargar la asistencia.")).toBeInTheDocument();
    // Un fallo de red NO puede afirmarse como "no hay sesiones con
    // asistencia": son dos hechos distintos y sólo uno es cierto.
    expect(
      screen.queryByText("Aún no hay sesiones con asistencia registrada"),
    ).not.toBeInTheDocument();
  });

  it("cold start: esqueleto, nunca tono de error ni la línea de vacío", () => {
    stubQuery({ isError: true, error: new Error("Network Error"), data: undefined });

    const { container } = render(<AttendanceMiniChart />);

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Cargando asistencia" })).toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(
      screen.queryByText("Aún no hay sesiones con asistencia registrada"),
    ).not.toBeInTheDocument();
  });

  it("cargando: mismo esqueleto que el cold start", () => {
    stubQuery({ isLoading: true, data: undefined });

    render(<AttendanceMiniChart />);

    expect(screen.getByRole("status", { name: "Cargando asistencia" })).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
