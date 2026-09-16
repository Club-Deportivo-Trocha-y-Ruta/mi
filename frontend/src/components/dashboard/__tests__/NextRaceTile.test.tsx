/**
 * Tests para NextRaceTile (specs/031-coach-home-mission-control, Tile 2
 * "Próxima carrera").
 *
 * Cubre:
 *  - skeleton mientras `useRaceEventsList` está en `isLoading`.
 *  - estado poblado, parametrizado por tier (A/B/C) en los `daysUntil`
 *    que cruzan cada umbral exacto de `contracts/home-tiles.md`:
 *      A → warning en daysUntil<=10, in_window en daysUntil<=7.
 *      B → warning en daysUntil<=6, in_window en daysUntil<=4.
 *      C → siempre neutral (sin ventana de tapering).
 *    El Campeonato Departamental (`priority: "CD"`) ya no es un tier "CD"
 *    separado (feature 033, T015): `tierFromPriority` lo resuelve a "A"
 *    (misma disciplina de tapering) — ver el caso dedicado más abajo.
 *  - estado vacío de fin de temporada (sin eventos con event_date >= hoy).
 *  - estado de error real (no cold start): ErrorState con "Reintentar".
 *  - cold start (`isColdStartError`): siempre skeleton, nunca tono de error.
 *
 * Mockea `@/hooks/race/useRaceEvents` completo (mismo patrón que
 * `NextSessionTile.test.tsx` mockeando el hook de datos en vez de la capa
 * HTTP), porque `NextRaceTile` consume únicamente `useRaceEventsList`.
 *
 * Wave 3 (hotfix multicopa, 2026-09-16): el tier ya no sale de un
 * calendario Copa Valle hardcodeado por mes (`getCarreraTier`, retirado de
 * `lib/insights.ts`) — sale de `RaceEventListItem.priority`, así que los
 * fixtures de este archivo fijan `priority` explícitamente en vez de
 * depender del mes del `event_date`.
 *
 * Fechas: cada caso fija "hoy" vía `vi.setSystemTime` y construye el
 * `event_date` del ítem como ISO datetime a mediodía UTC (`T12:00:00.000Z`,
 * = 07:00 America/Bogotá, sin cruce de día) para que `diffDaysFromToday`
 * (usa `CLUB_TIMEZONE`) resuelva el mismo día calendario sin ambigüedad.
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
    priority: null,
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

    expect(screen.getByText("Próxima carrera")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  describe("estado poblado — urgencia por tier, cruzando los umbrales exactos", () => {
    const UPCOMING_LABEL = "Se acerca la ventana de tapering";
    const IN_WINDOW_LABEL = "En ventana de tapering";

    it.each<{
      priority: "A" | "B" | "C" | "CD";
      taperLabel: string;
      daysUntil: number;
      expectedUrgency: "neutral" | "upcoming" | "in_window";
    }>([
      // Tier A — warning<=10, in_window<=7.
      { priority: "A", taperLabel: "A — Tapering completo", daysUntil: 11, expectedUrgency: "neutral" },
      { priority: "A", taperLabel: "A — Tapering completo", daysUntil: 10, expectedUrgency: "upcoming" },
      { priority: "A", taperLabel: "A — Tapering completo", daysUntil: 7, expectedUrgency: "in_window" },
      { priority: "A", taperLabel: "A — Tapering completo", daysUntil: 3, expectedUrgency: "in_window" },
      // Tier B — warning<=6, in_window<=4.
      { priority: "B", taperLabel: "B — Mini-tapering", daysUntil: 7, expectedUrgency: "neutral" },
      { priority: "B", taperLabel: "B — Mini-tapering", daysUntil: 6, expectedUrgency: "upcoming" },
      { priority: "B", taperLabel: "B — Mini-tapering", daysUntil: 4, expectedUrgency: "in_window" },
      { priority: "B", taperLabel: "B — Mini-tapering", daysUntil: 1, expectedUrgency: "in_window" },
      // Tier C — sin ventana de tapering: siempre neutral.
      { priority: "C", taperLabel: "C — Diagnóstica", daysUntil: 20, expectedUrgency: "neutral" },
      { priority: "C", taperLabel: "C — Diagnóstica", daysUntil: 0, expectedUrgency: "neutral" },
      // CD (campeonato) — Wave 3: tierFromPriority lo resuelve a "A" (misma
      // disciplina de tapering); la distinción de campeonato la sigue
      // llevando el badge "CD" aparte en CompetitionDetailPage.tsx, no esta
      // tile.
      { priority: "CD", taperLabel: "A — Tapering completo", daysUntil: 11, expectedUrgency: "neutral" },
      { priority: "CD", taperLabel: "A — Tapering completo", daysUntil: 10, expectedUrgency: "upcoming" },
      { priority: "CD", taperLabel: "A — Tapering completo", daysUntil: 7, expectedUrgency: "in_window" },
    ])(
      "priority $priority, daysUntil=$daysUntil → $expectedUrgency",
      ({ priority, taperLabel, daysUntil, expectedUrgency }) => {
        const eventDate = isoNoon(2026, 5, 20);
        vi.useFakeTimers();
        vi.setSystemTime(subDays(eventDate, daysUntil));

        const race = makeRaceEvent({
          id: 77,
          name: "Copa Valle — Próxima Válida",
          event_date: eventDate,
          location: "Cancha Ginebra",
          priority,
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

  // -------------------------------------------------------------------------
  // Feature 035 — insignia "Clase A/B/C" + línea de guía de tapering
  // -------------------------------------------------------------------------

  describe("insignia de clase y guía de tapering", () => {
    it("tier con ventana de tapering: chip 'Clase A' + rango real de TAPER_GUIDANCE", () => {
      const eventDate = isoNoon(2026, 5, 20);
      vi.useFakeTimers();
      vi.setSystemTime(subDays(eventDate, 20));

      mockUseRaceEventsList.mockReturnValue(
        makeQueryResult({
          data: {
            items: [
              makeRaceEvent({
                id: 77,
                name: "Copa Valle — Cali",
                event_date: eventDate,
                location: "Cali",
                priority: "A",
              }),
            ],
            total: 1,
          },
        }),
      );

      renderTile();

      // El chip lleva texto ("Clase A"), no sólo el punto de color.
      expect(screen.getByText("Clase A")).toBeInTheDocument();
      expect(screen.getByText("A — Tapering completo · 5–7 días")).toBeInTheDocument();
      // La guía de tapering ya no viaja comprimida dentro del hint.
      expect(screen.getByText("en 20 días · Cali")).toBeInTheDocument();
    });

    it("tier C (diagnóstica): chip 'Clase C' y copy de 'sin ventana de tapering'", () => {
      const eventDate = isoNoon(2026, 1, 20);
      vi.useFakeTimers();
      vi.setSystemTime(subDays(eventDate, 5));

      mockUseRaceEventsList.mockReturnValue(
        makeQueryResult({
          data: {
            items: [makeRaceEvent({ id: 78, event_date: eventDate, priority: "C" })],
            total: 1,
          },
        }),
      );

      renderTile();

      expect(screen.getByText("Clase C")).toBeInTheDocument();
      expect(screen.getByText("C — Diagnóstica · sin ventana de tapering")).toBeInTheDocument();
    });

    it("priority null (UNKNOWN): sin chip ni línea de tapering", () => {
      const eventDate = isoNoon(2026, 7, 20);
      vi.useFakeTimers();
      vi.setSystemTime(subDays(eventDate, 5));

      mockUseRaceEventsList.mockReturnValue(
        makeQueryResult({
          data: {
            items: [
              makeRaceEvent({
                id: 79,
                event_date: eventDate,
                location: "Ginebra",
                priority: null,
              }),
            ],
            total: 1,
          },
        }),
      );

      renderTile();

      expect(screen.queryByText(/^Clase /)).not.toBeInTheDocument();
      expect(screen.queryByText(/Tapering/)).not.toBeInTheDocument();
      expect(screen.getByText("en 5 días · Ginebra")).toBeInTheDocument();
    });
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
      priority: "CD",
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
    expect(screen.getByText("Próxima carrera")).toBeInTheDocument();
    expect(container.querySelector('[aria-hidden="true"]')).toBeInTheDocument();
  });
});
