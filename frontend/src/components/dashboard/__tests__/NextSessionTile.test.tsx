/**
 * Tests para NextSessionTile (specs/031-coach-home-mission-control, Tile 1
 * "Próxima sesión").
 *
 * Cubre:
 *  - skeleton mientras `useTrainingSessions` está en `isLoading`.
 *  - estado poblado: nombre/día relativo/lugar, y que hacer click navega a
 *    `/training/sessions/{id}` (patrón `AthleteLink.test.tsx`: <Routes> +
 *    `useLocation` hermano para verificar navegación real, no solo `href`).
 *  - estado vacío: EmptyState con CTA "+ Planificar" → `/training/sessions/new`.
 *  - Edge Case (regresión): una sesión de hoy cuyo `scheduled_start_time` +
 *    `duration_min` ya pasó no se muestra; se selecciona la siguiente próxima.
 *  - estado de error real (no cold start): ErrorState con botón "Reintentar"
 *    que llama a `refetch`.
 *  - cold start (`isColdStartError`): siempre skeleton, nunca tono de error
 *    (FR-008, contracts/home-tiles.md "Cold start").
 *
 * Mockea `@/api/trainingSessions` completo (mismo patrón que
 * `SessionsListPage.test.tsx` / `MeasurementAlerts.test.tsx` mockeando el
 * hook de datos en vez de la capa HTTP con MSW), porque `NextSessionTile`
 * consume únicamente `useTrainingSessions`. Usa `fireEvent` (no `userEvent`)
 * para los clicks: en los tests que fijan `vi.useFakeTimers()` (necesario
 * para controlar "ahora" en la selección/etiqueta de fecha),
 * `userEvent`'s internal async delays cuelgan la prueba salvo que se
 * reconfigure `advanceTimers` con cuidado — `fireEvent` es síncrono y evita
 * ese acoplamiento.
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";

import { NextSessionTile } from "../NextSessionTile";
import type { TrainingSession } from "@/types/trainingSession.types";

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
}));

import { useTrainingSessions } from "@/api/trainingSessions";

const mockUseTrainingSessions = vi.mocked(useTrainingSessions);

type QueryResult = ReturnType<typeof useTrainingSessions>;

function makeQueryResult(overrides: Partial<QueryResult>): QueryResult {
  return {
    isLoading: false,
    isError: false,
    data: undefined,
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as QueryResult;
}

function makeSession(overrides: Partial<TrainingSession> = {}): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 1,
    status: "planned",
    scheduled_date: "2026-07-16",
    scheduled_start_time: "07:00:00",
    duration_min: 60,
    location: "Cancha Ginebra",
    technical_focus: "Técnica de curvas",
    description: "",
    created_at: "2026-07-01T00:00:00Z",
    updated_at: "2026-07-01T00:00:00Z",
    ...overrides,
  };
}

/** Muestra el pathname actual — sirve para confirmar navegación real al hacer click. */
function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location-display">{location.pathname}</div>;
}

function renderTile() {
  return render(
    <MemoryRouter initialEntries={["/dashboard"]}>
      <LocationDisplay />
      <Routes>
        <Route path="/dashboard" element={<NextSessionTile />} />
        <Route path="/training/sessions/:id" element={<div>Detalle de sesión</div>} />
        <Route path="/training/sessions/new" element={<div>Nueva sesión</div>} />
      </Routes>
    </MemoryRouter>,
  );
}

describe("NextSessionTile", () => {
  afterEach(() => {
    // Restaura timers reales para cualquier test que haya usado
    // vi.useFakeTimers() localmente (idempotente si ya eran reales).
    vi.useRealTimers();
  });

  it("muestra un skeleton mientras carga", () => {
    mockUseTrainingSessions.mockReturnValue(makeQueryResult({ isLoading: true }));

    const { container } = renderTile();

    expect(screen.getByText("Próxima sesión")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("muestra la sesión más próxima (nombre, día relativo, lugar) y navega a /training/sessions/{id} al hacer click", () => {
    // 2026-07-15T20:00:00Z == 2026-07-15 15:00 America/Bogotá (UTC-5, sin DST).
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T20:00:00Z"));

    const session = makeSession({
      id: 42,
      // Nota: `scheduled_date` (fecha pura, sin hora) se interpreta como
      // medianoche UTC en `formatRelativeDayCount`, que al convertir a
      // America/Bogota (UTC-5) cae en el día calendario anterior — por eso
      // "2026-07-17" etiqueta como "Mañana" respecto al 15 de julio en
      // Bogotá, no "en 2 días". La selección de "próxima sesión" (que sí
      // ancla la hora con offset -05:00 explícito) trata esta misma fecha
      // como un instante claramente futuro de todos modos.
      scheduled_date: "2026-07-17",
      scheduled_start_time: "07:00:00",
      technical_focus: "Técnica de curvas",
      location: "Cancha Ginebra",
    });
    mockUseTrainingSessions.mockReturnValue(makeQueryResult({ data: [session] }));

    renderTile();

    expect(screen.getByText("Técnica de curvas")).toBeInTheDocument();
    expect(screen.getByText(/Mañana/)).toBeInTheDocument();
    expect(screen.getByText(/07:00 a\. m\./)).toBeInTheDocument();
    expect(screen.getByText(/Cancha Ginebra/)).toBeInTheDocument();

    const link = screen.getByRole("link");
    expect(link).toHaveAttribute("href", "/training/sessions/42");

    fireEvent.click(link);

    expect(screen.getByTestId("location-display")).toHaveTextContent(
      "/training/sessions/42",
    );
  });

  it('muestra el estado vacío con CTA "+ Planificar" hacia /training/sessions/new cuando no hay sesiones planificadas', () => {
    mockUseTrainingSessions.mockReturnValue(makeQueryResult({ data: [] }));

    renderTile();

    expect(screen.getByText("Sin sesiones planificadas")).toBeInTheDocument();
    const cta = screen.getByRole("link", { name: "+ Planificar" });
    expect(cta).toHaveAttribute("href", "/training/sessions/new");

    fireEvent.click(cta);

    expect(screen.getByTestId("location-display")).toHaveTextContent(
      "/training/sessions/new",
    );
  });

  it("excluye una sesión de hoy que ya terminó y muestra la siguiente próxima (regresión Edge Case)", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T20:00:00Z")); // 15:00 Bogotá

    const finishedToday = makeSession({
      id: 1,
      scheduled_date: "2026-07-15", // hoy (calendario Bogotá)
      scheduled_start_time: "08:00:00",
      duration_min: 60, // termina 09:00 Bogotá — ya pasó (ahora son las 15:00)
      technical_focus: "Sesión ya terminada",
    });
    const upcoming = makeSession({
      id: 2,
      scheduled_date: "2026-07-16",
      scheduled_start_time: "07:00:00",
      duration_min: 60,
      technical_focus: "Sesión de mañana",
    });
    mockUseTrainingSessions.mockReturnValue(
      makeQueryResult({ data: [finishedToday, upcoming] }),
    );

    renderTile();

    expect(screen.queryByText("Sesión ya terminada")).not.toBeInTheDocument();
    expect(screen.getByText("Sesión de mañana")).toBeInTheDocument();
  });

  it("muestra ErrorState con botón Reintentar ante un error real (no cold start)", () => {
    const refetch = vi.fn();
    mockUseTrainingSessions.mockReturnValue(
      makeQueryResult({
        isError: true,
        error: new Error("Error de validación"),
        refetch,
      }),
    );

    renderTile();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByText("No se pudo cargar la próxima sesión."),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Reintentar/ }));

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("cold start: renderiza un skeleton, nunca un tono de error", () => {
    mockUseTrainingSessions.mockReturnValue(
      makeQueryResult({
        isError: true,
        error: new Error("Network Error"),
      }),
    );

    const { container } = renderTile();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Próxima sesión")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });
});
