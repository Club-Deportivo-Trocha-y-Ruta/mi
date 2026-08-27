/**
 * Tests de WeekStrip — tarjeta "Semana en curso" del Inicio del coach
 * (feature 035, fila B del mockup `Main.dc.html`).
 *
 * Cubre:
 *  - las 7 celdas lunes→domingo de la semana ISO en curso (TZ del club) y el
 *    marcado de "hoy" por canales no cromáticos (etiqueta "hoy" + semibold),
 *  - la píldora por sesión (foco técnico + hora corta) y el "—" de los días
 *    sin sesión,
 *  - el check de sesión ejecutada, que llega por la ventana compartida con
 *    `AttendanceMiniChart`,
 *  - cold start → esqueletos y nunca tono de error; error real → línea
 *    neutra sin bloquear la tira,
 *  - el contrato de filtros compartidos con `NextSessionTile` /
 *    `AttendanceMiniChart` (misma queryKey ⇒ sin requests duplicados).
 *
 * "Hoy" se fija en 2026-08-27T20:00:00Z == jueves 27 de agosto, 15:00 en
 * America/Bogotá (UTC-5, sin DST) — semana ISO 35, lunes 24 → domingo 30.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import type { SessionFilters, TrainingSession } from "@/types/trainingSession.types";

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
}));

import { useTrainingSessions } from "@/api/trainingSessions";

import {
  WeekStrip,
  clubTodayIso,
  currentIsoWeekDays,
  currentIsoWeekNumber,
  executedSessionsFilters,
  plannedSessionsFilters,
} from "../WeekStrip";

const mockUseTrainingSessions = vi.mocked(useTrainingSessions);

type QueryResult = ReturnType<typeof useTrainingSessions>;

function makeSession(overrides: Partial<TrainingSession> = {}): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 1,
    status: "planned",
    scheduled_date: "2026-08-27",
    scheduled_start_time: "16:00:00",
    duration_min: 90,
    location: "Parque de la Salud",
    technical_focus: "Gymkhana",
    description: "",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

/**
 * El componente llama al hook DOS veces (ventana planificada + ventana
 * ejecutada). Se despacha por `filters.status` para poder alimentar cada
 * ventana por separado con un único mock.
 */
function stubSessions(options: {
  planned?: TrainingSession[];
  executed?: TrainingSession[];
  plannedState?: Partial<{ isLoading: boolean; isError: boolean; error: unknown }>;
  executedState?: Partial<{ isLoading: boolean; isError: boolean; error: unknown }>;
}) {
  mockUseTrainingSessions.mockImplementation(((filters?: SessionFilters) => {
    const isExecutedWindow = filters?.status === "executed";
    if (isExecutedWindow) {
      return {
        isLoading: false,
        isError: false,
        data: options.executed ?? [],
        error: null,
        refetch: vi.fn(),
        ...options.executedState,
      } as unknown as QueryResult;
    }
    return {
      isLoading: false,
      isError: false,
      data: options.planned ?? [],
      error: null,
      refetch: vi.fn(),
      ...options.plannedState,
    } as unknown as QueryResult;
  }) as typeof useTrainingSessions);
}

function renderStrip() {
  return render(
    <MemoryRouter>
      <WeekStrip />
    </MemoryRouter>,
  );
}

describe("WeekStrip", () => {
  beforeEach(() => {
    mockUseTrainingSessions.mockReset();
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-27T20:00:00Z"));
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  describe("ventanas compartidas de sesiones (misma queryKey ⇒ sin requests extra)", () => {
    it("plannedSessionsFilters() replica la ventana de NextSessionTile (hoy → +14 días, planned)", () => {
      expect(clubTodayIso()).toBe("2026-08-27");
      expect(plannedSessionsFilters()).toEqual({
        from_date: "2026-08-27",
        to_date: "2026-09-10",
        status: "planned",
      });
    });

    it("executedSessionsFilters() replica la ventana de AttendanceMiniChart (-60 días → hoy, executed)", () => {
      expect(executedSessionsFilters()).toEqual({
        from_date: "2026-06-28",
        to_date: "2026-08-27",
        status: "executed",
      });
    });

    it("currentIsoWeekDays()/currentIsoWeekNumber() resuelven la semana ISO en la TZ del club", () => {
      expect(currentIsoWeekNumber()).toBe(35);
      expect(currentIsoWeekDays()).toEqual([
        "2026-08-24",
        "2026-08-25",
        "2026-08-26",
        "2026-08-27",
        "2026-08-28",
        "2026-08-29",
        "2026-08-30",
      ]);
    });
  });

  it("renderiza los 7 días de la semana ISO en curso y enlaza al calendario", () => {
    stubSessions({});

    renderStrip();

    expect(screen.getByRole("heading", { name: "Semana en curso" })).toBeInTheDocument();
    for (const dayNumber of ["24", "25", "26", "27", "28", "29", "30"]) {
      expect(screen.getByText(dayNumber)).toBeInTheDocument();
    }

    const link = screen.getByRole("link", { name: "Abrir calendario" });
    expect(link).toHaveAttribute("href", "/calendar");
    // Objetivo táctil ≥44px (Constitution III).
    expect(link.className).toMatch(/min-h-11/);
    // Tinta legible: el turquesa de marca sobre la tarjeta blanca da 2.42:1.
    expect(link.className).toMatch(/text-charcoal/);
    expect(link.className).toMatch(/underline/);
  });

  it('marca "hoy" con etiqueta + semibold + círculo relleno (el color nunca es el único canal)', () => {
    stubSessions({});

    renderStrip();

    const todayLabel = screen.getByText(/hoy/);
    expect(todayLabel.className).toMatch(/font-semibold/);
    // La etiqueta se queda en charcoal: el acento sobre el tinte de la celda
    // da 4.09:1 y no pasa AA. El color lo llevan el círculo y el tinte.
    expect(todayLabel.className).toMatch(/text-charcoal/);
    expect(todayLabel.className).not.toMatch(/text-nav-accent/);

    const todayNumber = screen.getByText("27");
    expect(todayNumber.className).toMatch(/bg-primary/);
    expect(todayNumber.className).toMatch(/rounded-full/);
    // Tinta oscura sobre el relleno turquesa (7.8:1); blanco daba 2.42:1.
    expect(todayNumber.className).toMatch(/text-midnight/);

    // Ningún otro día lleva el círculo relleno.
    expect(screen.getByText("24").className).not.toMatch(/bg-primary/);
  });

  it("muestra una píldora por sesión planificada (foco + hora corta) y '—' en los días sin sesión", () => {
    stubSessions({
      planned: [
        makeSession({ id: 10, scheduled_date: "2026-08-27", scheduled_start_time: "16:00:00" }),
        makeSession({
          id: 11,
          scheduled_date: "2026-08-29",
          scheduled_start_time: "08:30:00",
          technical_focus: "Técnica",
        }),
      ],
    });

    renderStrip();

    expect(screen.getByText(/Gymkhana\s+4\s*p\.?\s*m\.?/)).toBeInTheDocument();
    expect(screen.getByText(/Técnica\s+8:30\s*a\.?\s*m\.?/)).toBeInTheDocument();
    // 7 días - 2 con sesión = 5 celdas vacías.
    expect(screen.getAllByText("—")).toHaveLength(5);
  });

  it("distingue una sesión ejecutada con un check y su equivalente textual", () => {
    stubSessions({
      executed: [
        makeSession({
          id: 20,
          status: "executed",
          scheduled_date: "2026-08-25",
          scheduled_start_time: "17:00:00",
          technical_focus: "Resistencia Z2",
        }),
      ],
    });

    const { container } = renderStrip();

    expect(screen.getByText(/Resistencia Z2/)).toBeInTheDocument();
    expect(screen.getByText("Ejecutada:")).toBeInTheDocument();
    expect(container.querySelector(".text-success")).toBeInTheDocument();
  });

  it("ignora las sesiones fuera de la semana en curso", () => {
    stubSessions({
      planned: [
        makeSession({ id: 30, scheduled_date: "2026-09-03", technical_focus: "Fuera de semana" }),
      ],
    });

    renderStrip();

    expect(screen.queryByText(/Fuera de semana/)).not.toBeInTheDocument();
    expect(screen.getAllByText("—")).toHaveLength(7);
  });

  it("cold start: esqueletos en vez de sesiones, nunca un tono de error", () => {
    stubSessions({
      plannedState: {
        isLoading: false,
        isError: true,
        error: new Error("Network Error"),
      },
    });

    const { container } = renderStrip();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByRole("status", { name: "Cargando la semana en curso" }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("error real: la tira sigue visible con una línea neutra (nunca bloquea el Inicio)", () => {
    stubSessions({
      plannedState: {
        isLoading: false,
        isError: true,
        error: new Error("Error de validación"),
      },
    });

    renderStrip();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.getByText("No se pudieron cargar las sesiones de esta semana."),
    ).toBeInTheDocument();
    // Las fechas siguen siendo útiles aunque las sesiones no carguen.
    expect(screen.getByText("27")).toBeInTheDocument();
  });

  // La ventana ejecutada es la ÚNICA fuente de lunes→ayer (la planificada
  // arranca hoy): si sólo se mirara la planificada, un fallo suyo pintaría
  // "—" en los días pasados y el coach lo leería como "no hubo entrenos".
  it("error real de la ventana ejecutada: misma línea neutra, nunca '—' en los días pasados", () => {
    stubSessions({
      executedState: {
        isLoading: false,
        isError: true,
        error: new Error("Error de validación"),
      },
    });

    renderStrip();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    // Mismo contrato que el error de la ventana planificada: la tira sigue
    // visible (las fechas son útiles) pero el "—" ya no queda solo — la
    // línea neutra dice que las sesiones no cargaron.
    expect(
      screen.getByText("No se pudieron cargar las sesiones de esta semana."),
    ).toBeInTheDocument();
    expect(screen.getByText("27")).toBeInTheDocument();
  });

  it("la ventana ejecutada aún en vuelo mantiene los esqueletos, no el '—' de 'sin sesiones'", () => {
    stubSessions({ executedState: { isLoading: true } });

    const { container } = renderStrip();

    expect(
      screen.getByRole("status", { name: "Cargando la semana en curso" }),
    ).toBeInTheDocument();
    expect(container.querySelectorAll(".animate-pulse").length).toBeGreaterThan(0);
    expect(screen.queryByText("—")).not.toBeInTheDocument();
  });

  it("cold start de la ventana ejecutada: esqueletos, nunca tono de error", () => {
    stubSessions({
      executedState: {
        isLoading: false,
        isError: true,
        error: new Error("Network Error"),
      },
    });

    renderStrip();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(
      screen.queryByText("No se pudieron cargar las sesiones de esta semana."),
    ).not.toBeInTheDocument();
    expect(
      screen.getByRole("status", { name: "Cargando la semana en curso" }),
    ).toBeInTheDocument();
  });
});
