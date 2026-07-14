/**
 * Tests para NextRaceTile (specs/031-coach-home-mission-control, Tile 2
 * "Próxima carrera Copa Valle").
 *
 * Cubre:
 *  - skeleton mientras `useRaceEventsList` está en `isLoading`.
 *  - estado poblado, parametrizado por tier (A/B/C) en los `daysUntil`
 *    que cruzan cada umbral exacto de `contracts/home-tiles.md`:
 *      A → warning en daysUntil<=10, in_window en daysUntil<=7.
 *      B → warning en daysUntil<=6, in_window en daysUntil<=4.
 *      C → siempre neutral (sin ventana de tapering).
 *    El Campeonato Departamental (junio) ya no es un tier "CD" separado
 *    (feature 033, T015): `getCarreraTier` lo resuelve a "A", así que el
 *    mes de junio se cubre con el mismo caso `tier: "A"` (ver el caso
 *    dedicado más abajo que fija `month: 6` para probar ese mes puntual).
 *  - estado vacío de fin de temporada (sin eventos con event_date >= hoy).
 *  - estado de error real (no cold start): ErrorState con "Reintentar".
 *  - cold start (`isColdStartError`): siempre skeleton, nunca tono de error.
 *
 * Mockea `@/hooks/race/useRaceEvents` completo (mismo patrón que
 * `NextSessionTile.test.tsx` mockeando el hook de datos en vez de la capa
 * HTTP), porque `NextRaceTile` consume únicamente `useRaceEventsList`.
 *
 * Fechas: cada caso fija "hoy" vía `vi.setSystemTime` y construye el
 * `event_date` del ítem como ISO datetime a mediodía UTC (`T12:00:00.000Z`,
 * = 07:00 America/Bogotá, sin cruce de día) para que tanto
 * `diffDaysFromToday` (usa `CLUB_TIMEZONE`) como `getCarreraTier` (usa
 * `Date.getMonth()` en la TZ local del proceso) resuelvan el mismo día
 * calendario sin ambigüedad. El día-del-mes del evento se fija en 20 (nunca
 * varía entre casos) para que el mes — y por lo tanto el tier — se mantenga
 * estable sin importar cuánto se reste al construir "hoy".
 */
import { afterEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";

import { NextRaceTile } from "../NextRaceTile";
import type { RaceEventListItem } from "@/types/raceEvents.types";

vi.mock("@/hooks/race/useRaceEvents", () => ({
  useRaceEventsList: vi.fn(),
}));

import { useRaceEventsList } from "@/hooks/race/useRaceEvents";

const mockUseRaceEventsList = vi.mocked(useRaceEventsList);

type QueryResult = ReturnType<typeof useRaceEventsList>;

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

function makeRaceEvent(overrides: Partial<RaceEventListItem> = {}): RaceEventListItem {
  return {
    id: 1,
    series_id: 1,
    sequence_number: 1,
    name: "Copa Valle — Ginebra",
    event_date: "2026-05-20T12:00:00.000Z",
    location: "Ginebra",
    is_championship: false,
    status: "scheduled",
    has_results: false,
    has_calendar_event: false,
    conditions_completeness: "empty",
    ...overrides,
  } as RaceEventListItem;
}

/** Mediodía UTC del día indicado — evita ambigüedad de cruce de día entre TZs. */
function isoNoon(year: number, month: number, day: number): string {
  return new Date(Date.UTC(year, month - 1, day, 12, 0, 0)).toISOString();
}

/** Resta `days` días calendario (UTC) a un ISO string, preservando la hora. */
function subDays(iso: string, days: number): Date {
  const d = new Date(iso);
  d.setUTCDate(d.getUTCDate() - days);
  return d;
}

function renderTile() {
  return render(
    <MemoryRouter>
      <NextRaceTile />
    </MemoryRouter>,
  );
}

describe("NextRaceTile", () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it("muestra un skeleton mientras carga", () => {
    mockUseRaceEventsList.mockReturnValue(makeQueryResult({ isLoading: true }));

    const { container } = renderTile();

    expect(screen.getByText("Próxima carrera Copa Valle")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  describe("estado poblado — urgencia por tier, cruzando los umbrales exactos", () => {
    const UPCOMING_LABEL = "Se acerca la ventana de tapering";
    const IN_WINDOW_LABEL = "En ventana de tapering";

    it.each<{
      tier: "A" | "B" | "C";
      month: number;
      taperLabel: string;
      daysUntil: number;
      expectedUrgency: "neutral" | "upcoming" | "in_window";
    }>([
      // Tier A (mayo) — warning<=10, in_window<=7.
      { tier: "A", month: 5, taperLabel: "A — Tapering completo", daysUntil: 11, expectedUrgency: "neutral" },
      { tier: "A", month: 5, taperLabel: "A — Tapering completo", daysUntil: 10, expectedUrgency: "upcoming" },
      { tier: "A", month: 5, taperLabel: "A — Tapering completo", daysUntil: 7, expectedUrgency: "in_window" },
      { tier: "A", month: 5, taperLabel: "A — Tapering completo", daysUntil: 3, expectedUrgency: "in_window" },
      // Tier B (agosto) — warning<=6, in_window<=4.
      { tier: "B", month: 8, taperLabel: "B — Mini-tapering", daysUntil: 7, expectedUrgency: "neutral" },
      { tier: "B", month: 8, taperLabel: "B — Mini-tapering", daysUntil: 6, expectedUrgency: "upcoming" },
      { tier: "B", month: 8, taperLabel: "B — Mini-tapering", daysUntil: 4, expectedUrgency: "in_window" },
      { tier: "B", month: 8, taperLabel: "B — Mini-tapering", daysUntil: 1, expectedUrgency: "in_window" },
      // Tier C (enero) — sin ventana de tapering: siempre neutral.
      { tier: "C", month: 1, taperLabel: "C — Diagnóstica", daysUntil: 20, expectedUrgency: "neutral" },
      { tier: "C", month: 1, taperLabel: "C — Diagnóstica", daysUntil: 0, expectedUrgency: "neutral" },
      // Junio (Campeonato Departamental) — feature 033/T015: getCarreraTier
      // ya no devuelve "CD", resuelve a "A" (misma disciplina de tapering);
      // la distinción de campeonato la sigue llevando el badge "CD" aparte
      // en CompetitionDetailPage.tsx, no esta tile.
      { tier: "A", month: 6, taperLabel: "A — Tapering completo", daysUntil: 11, expectedUrgency: "neutral" },
      { tier: "A", month: 6, taperLabel: "A — Tapering completo", daysUntil: 10, expectedUrgency: "upcoming" },
      { tier: "A", month: 6, taperLabel: "A — Tapering completo", daysUntil: 7, expectedUrgency: "in_window" },
    ])(
      "tier $tier, daysUntil=$daysUntil → $expectedUrgency",
      ({ month, taperLabel, daysUntil, expectedUrgency }) => {
        const eventDate = isoNoon(2026, month, 20);
        vi.useFakeTimers();
        vi.setSystemTime(subDays(eventDate, daysUntil));

        const race = makeRaceEvent({
          id: 77,
          name: "Copa Valle — Próxima Válida",
          event_date: eventDate,
          location: "Cancha Ginebra",
        });
        mockUseRaceEventsList.mockReturnValue(
          makeQueryResult({ data: { items: [race], total: 1 } }),
        );

        renderTile();

        // Valor + hint: nombre de la carrera, lugar y guía de tapering del tier.
        expect(screen.getByText("Copa Valle — Próxima Válida")).toBeInTheDocument();
        expect(screen.getByText(new RegExp("Cancha Ginebra"))).toBeInTheDocument();
        expect(screen.getByText(new RegExp(taperLabel.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")))).toBeInTheDocument();

        // Link a la carrera.
        const link = screen.getByRole("link");
        expect(link).toHaveAttribute("href", "/competitions/77");

        // Insignia de urgencia — el color nunca es el único canal (icono + texto).
        if (expectedUrgency === "neutral") {
          expect(screen.queryByText(UPCOMING_LABEL)).not.toBeInTheDocument();
          expect(screen.queryByText(IN_WINDOW_LABEL)).not.toBeInTheDocument();
        } else if (expectedUrgency === "upcoming") {
          expect(screen.getByText(UPCOMING_LABEL)).toBeInTheDocument();
          expect(screen.queryByText(IN_WINDOW_LABEL)).not.toBeInTheDocument();
        } else {
          expect(screen.getByText(IN_WINDOW_LABEL)).toBeInTheDocument();
          expect(screen.queryByText(UPCOMING_LABEL)).not.toBeInTheDocument();
        }
      },
    );
  });

  it('muestra "Temporada finalizada — sin próximas carreras" cuando no hay eventos futuros en la temporada', () => {
    mockUseRaceEventsList.mockReturnValue(
      makeQueryResult({ data: { items: [], total: 0 } }),
    );

    renderTile();

    expect(
      screen.getByText("Temporada finalizada — sin próximas carreras"),
    ).toBeInTheDocument();
    expect(screen.queryByRole("link")).not.toBeInTheDocument();
  });

  it("estado vacío también aplica cuando todos los eventos de la lista ya pasaron", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T20:00:00.000Z"));

    const pastRace = makeRaceEvent({
      id: 5,
      event_date: isoNoon(2026, 6, 12), // Campeonato Departamental — ya pasado.
    });
    mockUseRaceEventsList.mockReturnValue(
      makeQueryResult({ data: { items: [pastRace], total: 1 } }),
    );

    renderTile();

    expect(
      screen.getByText("Temporada finalizada — sin próximas carreras"),
    ).toBeInTheDocument();
  });

  it("muestra ErrorState con botón Reintentar ante un error real (no cold start)", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    mockUseRaceEventsList.mockReturnValue(
      makeQueryResult({
        isError: true,
        error: new Error("Error de validación"),
        refetch,
      }),
    );

    renderTile();

    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(
      screen.getByText("No se pudo cargar la próxima carrera."),
    ).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /Reintentar/ }));

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("cold start: renderiza un skeleton, nunca un tono de error", () => {
    mockUseRaceEventsList.mockReturnValue(
      makeQueryResult({
        isError: true,
        error: new Error("Network Error"),
      }),
    );

    const { container } = renderTile();

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText("Próxima carrera Copa Valle")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });
});
