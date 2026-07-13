/**
 * Tests para PendingInbox (specs/031-coach-home-mission-control, Row 2
 * "Pending-work inbox", T033-T036).
 *
 * Cubre, para cada una de las 5 filas de forma independiente (T038):
 *  - cargando  → `state=undefined` en la fila objetivo (baseline resuelto en
 *    las otras 4) → la fila objetivo no muestra su etiqueta (solo esqueleto)
 *    mientras las demás sí renderizan su contenido.
 *  - poblada   → conteo correcto derivado de la fuente real + `href` del
 *    `<Link>` correcto por fila, per `contracts/home-tiles.md`.
 *  - omitida cuando `null` (fuente no disponible / error) → la fila objetivo
 *    desaparece por completo (FR-004), y el resto sigue visible.
 *
 * Mockea los 4 hooks de datos que `PendingInbox.tsx` consume directamente
 * (mismo patrón que `NextRaceTile.test.tsx` / `MeasurementAlerts.test.tsx`:
 * mock del hook, no de la capa HTTP), porque las filas 4-5 comparten una
 * ÚNICA instancia de `useCoachSummary()`.
 *
 * También cubre (T039) el estado "todo al día" (T037,
 * `contracts/home-tiles.md` §"All-clear state"): se muestra únicamente
 * cuando TODA fila resuelta reporta `count === 0` y ninguna sigue en
 * `undefined`/cargando.
 *
 * Caso degradado con MSW (T040/T041, US2 acceptance #2, FR-004): se
 * ejercitan de verdad los handlers `coachSummaryServerErrorHandler` /
 * `activitiesCountOnlyErrorHandler` de `dashboardHandlers.ts` contra la capa
 * HTTP real (`fetchCoachSummary`/`getActivities`, vía `mswServer`) para
 * fundamentar en un fallo real de red los estados `isError` que luego se
 * inyectan en los hooks mockeados (mismo patrón de mock-de-hook que el resto
 * de este archivo — no se reemplaza el `QueryClientProvider` real porque
 * `PendingInbox` no lo requiere directamente, son sus hooks quienes lo
 * consumirían). Así el escenario "1-2 filas no disponibles" queda anclado a
 * los fixtures MSW de T040, no a un `Error` inventado a mano.
 */
import { describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { PendingInbox } from "../PendingInbox";
import { currentSeason } from "@/lib/datetime";
import type { RaceEventListItem } from "@/types/raceEvents.types";
import type { ActivityListResponse } from "@/types/strava.types";
import type { NewsletterStatusSummary } from "@/hooks/training/useNewsletterStatusSummary";
import type { CoachSummary } from "@/types/dashboard.types";
import { mswServer } from "@/test/setup";
import {
  coachSummaryServerErrorHandler,
  activitiesCountOnlyErrorHandler,
} from "@/test/msw/dashboardHandlers";
import { fetchCoachSummary } from "@/api/dashboard";
import { getActivities } from "@/api/stravaActivities";

vi.mock("@/hooks/race/useRaceEvents", () => ({
  useRaceEventsList: vi.fn(),
}));
vi.mock("@/hooks/activities/useActivityReview", () => ({
  useActivityReview: vi.fn(),
}));
vi.mock("@/hooks/training/useNewsletterStatusSummary", () => ({
  useNewsletterStatusSummary: vi.fn(),
}));
vi.mock("@/hooks/dashboard/useCoachSummary", () => ({
  useCoachSummary: vi.fn(),
}));

// T050 (US4) — la fila "Consentimientos pendientes" ahora gatea su `<Link>`
// por rol (mismo patrón que `AthleteLink`, specs/028); ninguno de los tests
// de este archivo ejercita el rol, así que se fija "coach" (rol permitido
// en `/athletes`) para que el resto de aserciones existentes (que sí
// esperan un `<a>`) sigan siendo válidas. El caso admin queda cubierto en
// `DashboardPage.test.tsx` (T049).
vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { user: { id: number; role: string } | null }) => unknown) =>
    selector({ user: { id: 1, role: "coach" } }),
}));

import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { useActivityReview } from "@/hooks/activities/useActivityReview";
import { useNewsletterStatusSummary } from "@/hooks/training/useNewsletterStatusSummary";
import { useCoachSummary } from "@/hooks/dashboard/useCoachSummary";

const mockUseRaceEventsList = vi.mocked(useRaceEventsList);
const mockUseActivityReview = vi.mocked(useActivityReview);
const mockUseNewsletterStatusSummary = vi.mocked(useNewsletterStatusSummary);
const mockUseCoachSummary = vi.mocked(useCoachSummary);

// ---------------------------------------------------------------------------
// Helpers — estados "resueltos" (poblados) por defecto para las 5 fuentes,
// de forma que cada test pueda pisar SOLO la fila bajo prueba y dejar las
// otras 4 en un estado visible/estable (patrón "una variable a la vez").
// ---------------------------------------------------------------------------

type RaceQueryResult = ReturnType<typeof useRaceEventsList>;
type ActivityQueryResult = ReturnType<typeof useActivityReview>;
type NewsletterQueryResult = ReturnType<typeof useNewsletterStatusSummary>;
type CoachSummaryQueryResult = ReturnType<typeof useCoachSummary>;

function makeRaceEvent(overrides: Partial<RaceEventListItem> = {}): RaceEventListItem {
  return {
    id: 1,
    series_id: 1,
    sequence_number: 1,
    name: "Copa Valle — Ginebra",
    event_date: "2020-01-10T12:00:00.000Z",
    location: "Ginebra",
    is_championship: false,
    status: "scheduled",
    has_results: false,
    has_calendar_event: false,
    conditions_completeness: "empty",
    ...overrides,
  } as RaceEventListItem;
}

function raceResolved(overrides: Partial<RaceQueryResult> = {}): RaceQueryResult {
  return {
    isLoading: false,
    isError: false,
    data: {
      items: [
        // Pasada, sin resultados → cuenta.
        makeRaceEvent({ id: 1, event_date: "2020-01-10T12:00:00.000Z", has_results: false }),
        // Pasada, ya con resultados → NO cuenta.
        makeRaceEvent({ id: 2, event_date: "2020-02-10T12:00:00.000Z", has_results: true }),
        // Futura, sin resultados → NO cuenta (aún no corre).
        makeRaceEvent({ id: 3, event_date: "2099-01-10T12:00:00.000Z", has_results: false }),
        // Pasada, sin resultados → cuenta.
        makeRaceEvent({ id: 4, event_date: "2020-03-10T12:00:00.000Z", has_results: false }),
      ],
      total: 4,
    },
    error: null,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as RaceQueryResult;
}

function activitiesResolved(
  overrides: Partial<ActivityListResponse> = {},
): ActivityQueryResult {
  return {
    isLoading: false,
    isError: false,
    data: { items: [], total: 6, ...overrides },
    error: null,
    refetch: vi.fn(),
  } as unknown as ActivityQueryResult;
}

function newslettersResolved(
  overrides: Partial<NewsletterStatusSummary> = {},
): NewsletterQueryResult {
  return {
    isLoading: false,
    isError: false,
    data: {
      year: 2026,
      month: 7,
      items: [
        { athlete_id: 1, newsletter_id: 1, status: "sent", generated_at: "2026-07-01T00:00:00Z", sent_at: "2026-07-02T00:00:00Z" },
        { athlete_id: 2, newsletter_id: 2, status: "draft", generated_at: "2026-07-01T00:00:00Z", sent_at: null },
        { athlete_id: 3, newsletter_id: 3, status: "approved", generated_at: "2026-07-01T00:00:00Z", sent_at: null },
      ],
      ...overrides,
    },
    error: null,
    refetch: vi.fn(),
  } as unknown as NewsletterQueryResult;
}

function coachSummaryResolved(overrides: Partial<CoachSummary> = {}): CoachSummaryQueryResult {
  return {
    isLoading: false,
    isError: false,
    data: {
      generated_at: "2026-07-11T12:00:00Z",
      consents_pending: 5,
      insights_stale: 3,
      weekly_load: null,
      ...overrides,
    },
    error: null,
    refetch: vi.fn(),
  } as unknown as CoachSummaryQueryResult;
}

/** Fija las 4 fuentes a su estado poblado por defecto. */
function setAllResolved() {
  mockUseRaceEventsList.mockReturnValue(raceResolved());
  mockUseActivityReview.mockReturnValue(activitiesResolved());
  mockUseNewsletterStatusSummary.mockReturnValue(newslettersResolved());
  mockUseCoachSummary.mockReturnValue(coachSummaryResolved());
}

function renderInbox() {
  return render(
    <MemoryRouter>
      <PendingInbox />
    </MemoryRouter>,
  );
}

const LABELS = {
  results: "Resultados por importar",
  activities: "Actividades sin enlazar",
  newsletters: "Boletines pendientes del mes",
  consents: "Consentimientos pendientes",
  insights: "Insights IA desactualizados",
} as const;

describe("PendingInbox", () => {
  describe('fila "Resultados por importar" (T033)', () => {
    it("muestra un esqueleto mientras carga, sin ocultar las demás filas", () => {
      setAllResolved();
      mockUseRaceEventsList.mockReturnValue(
        raceResolved({ isLoading: true, data: undefined }),
      );

      renderInbox();

      expect(screen.queryByText(LABELS.results)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });

    it("poblada: cuenta solo carreras pasadas sin resultados y enlaza al filtro needs-results", () => {
      setAllResolved();

      renderInbox();

      const link = screen.getByText(LABELS.results).closest("a");
      expect(link).toHaveAttribute("href", "/competitions?filter=needs-results");
      expect(link).toHaveTextContent("2"); // 2 de los 4 ítems califican.
    });

    it("se omite por completo cuando la fuente falla (isError)", () => {
      setAllResolved();
      mockUseRaceEventsList.mockReturnValue(raceResolved({ isError: true, data: undefined }));

      renderInbox();

      expect(screen.queryByText(LABELS.results)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });
  });

  describe('fila "Actividades sin enlazar" (T034)', () => {
    it("muestra un esqueleto mientras carga, sin ocultar las demás filas", () => {
      setAllResolved();
      mockUseActivityReview.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as ActivityQueryResult);

      renderInbox();

      expect(screen.queryByText(LABELS.activities)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });

    it("poblada: usa el total de la respuesta paginada y enlaza a /activities?linked=false", () => {
      setAllResolved();
      mockUseActivityReview.mockReturnValue(activitiesResolved({ total: 12 }));

      renderInbox();

      const link = screen.getByText(LABELS.activities).closest("a");
      expect(link).toHaveAttribute("href", "/activities?linked=false");
      expect(link).toHaveTextContent("12");
    });

    it("se omite por completo cuando la fuente falla (isError)", () => {
      setAllResolved();
      mockUseActivityReview.mockReturnValue({
        isLoading: false,
        isError: true,
        data: undefined,
        error: new Error("network"),
        refetch: vi.fn(),
      } as unknown as ActivityQueryResult);

      renderInbox();

      expect(screen.queryByText(LABELS.activities)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });
  });

  describe('fila "Boletines pendientes del mes" (T035)', () => {
    it("muestra un esqueleto mientras carga, sin ocultar las demás filas", () => {
      setAllResolved();
      mockUseNewsletterStatusSummary.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as NewsletterQueryResult);

      renderInbox();

      expect(screen.queryByText(LABELS.newsletters)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });

    it('poblada: cuenta ítems con status !== "sent" y enlaza a /training/athlete-newsletters', () => {
      setAllResolved();

      renderInbox();

      const link = screen.getByText(LABELS.newsletters).closest("a");
      expect(link).toHaveAttribute("href", "/training/athlete-newsletters");
      expect(link).toHaveTextContent("2"); // draft + generated, sent excluido.
    });

    it("se omite por completo cuando la fuente falla (isError)", () => {
      setAllResolved();
      mockUseNewsletterStatusSummary.mockReturnValue({
        isLoading: false,
        isError: true,
        data: undefined,
        error: new Error("network"),
        refetch: vi.fn(),
      } as unknown as NewsletterQueryResult);

      renderInbox();

      expect(screen.queryByText(LABELS.newsletters)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });
  });

  describe('fila "Consentimientos pendientes" (T036)', () => {
    it("muestra un esqueleto mientras carga, sin ocultar las demás filas", () => {
      setAllResolved();
      mockUseCoachSummary.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as CoachSummaryQueryResult);

      renderInbox();

      // La carga de useCoachSummary afecta ambas filas 4 y 5 a la vez
      // (comparten la misma instancia del hook) — se valida aquí que
      // "consentimientos" no aparece; la fila de insights se valida en su
      // propio bloque de tests.
      expect(screen.queryByText(LABELS.consents)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
    });

    it("poblada: usa consents_pending y enlaza a /athletes", () => {
      setAllResolved();
      mockUseCoachSummary.mockReturnValue(coachSummaryResolved({ consents_pending: 7 }));

      renderInbox();

      const link = screen.getByText(LABELS.consents).closest("a");
      expect(link).toHaveAttribute("href", "/athletes");
      expect(link).toHaveTextContent("7");
    });

    it("se omite por completo cuando consents_pending es null (falla parcial del backend)", () => {
      setAllResolved();
      mockUseCoachSummary.mockReturnValue(coachSummaryResolved({ consents_pending: null }));

      renderInbox();

      expect(screen.queryByText(LABELS.consents)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
      // insights_stale sigue resuelto (5) → la fila de insights permanece visible.
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });

    it("se omite por completo cuando la fuente falla (isError)", () => {
      setAllResolved();
      mockUseCoachSummary.mockReturnValue({
        isLoading: false,
        isError: true,
        data: undefined,
        error: new Error("network"),
        refetch: vi.fn(),
      } as unknown as CoachSummaryQueryResult);

      renderInbox();

      expect(screen.queryByText(LABELS.consents)).not.toBeInTheDocument();
      expect(screen.queryByText(LABELS.insights)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
    });
  });

  describe('fila "Insights IA desactualizados" (T036)', () => {
    it("poblada: usa insights_stale y enlaza a /competitions/insights/season/{temporada actual}", () => {
      setAllResolved();
      mockUseCoachSummary.mockReturnValue(coachSummaryResolved({ insights_stale: 4 }));

      renderInbox();

      const link = screen.getByText(LABELS.insights).closest("a");
      expect(link).toHaveAttribute(
        "href",
        `/competitions/insights/season/${currentSeason()}`,
      );
      expect(link).toHaveTextContent("4");
    });

    it("se omite por completo cuando insights_stale es null (falla parcial del backend)", () => {
      setAllResolved();
      mockUseCoachSummary.mockReturnValue(coachSummaryResolved({ insights_stale: null }));

      renderInbox();

      expect(screen.queryByText(LABELS.insights)).not.toBeInTheDocument();
      // consents_pending sigue resuelto (5) → la fila de consentimientos permanece visible.
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.activities)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
    });
  });

  describe('estado "todo al día" (T037/T039)', () => {
    /** Fija las 5 fuentes a un estado resuelto donde CADA fila cuenta 0. */
    function setAllResolvedZero() {
      mockUseRaceEventsList.mockReturnValue(
        raceResolved({
          data: {
            items: [
              // Pasada, pero YA con resultados → no cuenta.
              makeRaceEvent({ id: 1, event_date: "2020-01-10T12:00:00.000Z", has_results: true }),
              // Futura, sin resultados → no cuenta (aún no corre).
              makeRaceEvent({ id: 2, event_date: "2099-01-10T12:00:00.000Z", has_results: false }),
            ],
            total: 2,
          },
        }),
      );
      mockUseActivityReview.mockReturnValue(activitiesResolved({ total: 0 }));
      mockUseNewsletterStatusSummary.mockReturnValue(
        newslettersResolved({
          items: [
            {
              athlete_id: 1,
              newsletter_id: 1,
              status: "sent",
              generated_at: "2026-07-01T00:00:00Z",
              sent_at: "2026-07-02T00:00:00Z",
            },
          ],
        }),
      );
      mockUseCoachSummary.mockReturnValue(
        coachSummaryResolved({ consents_pending: 0, insights_stale: 0 }),
      );
    }

    it("se muestra cuando las 5 filas resueltas reportan count === 0", () => {
      setAllResolvedZero();

      renderInbox();

      expect(
        screen.getByText("Todo al día — sin pendientes esta semana"),
      ).toBeInTheDocument();
      // La lista normal de filas (con sus links/contadores) desaparece: el
      // all-clear la reemplaza por completo, no coexiste con ella.
      expect(screen.queryByText(LABELS.results)).not.toBeInTheDocument();
      expect(screen.queryByText(LABELS.activities)).not.toBeInTheDocument();
      expect(screen.queryByText(LABELS.newsletters)).not.toBeInTheDocument();
      expect(screen.queryByText(LABELS.consents)).not.toBeInTheDocument();
      expect(screen.queryByText(LABELS.insights)).not.toBeInTheDocument();
    });

    it("NO se muestra mientras alguna fila sigue en undefined/cargando", () => {
      setAllResolvedZero();
      // Una sola fuente (actividades) todavía cargando; el resto ya
      // resolvió a 0 — esto NO debe bastar para el all-clear.
      mockUseActivityReview.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as ActivityQueryResult);

      renderInbox();

      expect(
        screen.queryByText("Todo al día — sin pendientes esta semana"),
      ).not.toBeInTheDocument();
      // La fila en `undefined` se mantiene como esqueleto (sin su etiqueta);
      // las demás, ya resueltas en 0, se listan normalmente.
      expect(screen.queryByText(LABELS.activities)).not.toBeInTheDocument();
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();
      expect(screen.getByText(LABELS.consents)).toBeInTheDocument();
      expect(screen.getByText(LABELS.insights)).toBeInTheDocument();
    });
  });

  describe("estado degradado con handlers MSW (T040/T041, US2 acceptance #2, FR-004)", () => {
    it("1-2 filas no disponibles (coach-summary 500 + actividades 500 vía MSW): el resto sigue visible y no aparece ningún banner de error", async () => {
      setAllResolved();
      mswServer.use(coachSummaryServerErrorHandler, activitiesCountOnlyErrorHandler);

      // Ancla el estado `isError` inyectado abajo a un fallo de red real
      // producido por los handlers MSW de T040 (no un `Error` inventado a
      // mano) — ejercita `fetchCoachSummary`/`getActivities`, las mismas
      // queryFn que `useCoachSummary`/`useActivityReview` usan internamente.
      await expect(fetchCoachSummary()).rejects.toBeTruthy();
      await expect(
        getActivities({ linked: "false", page: 1, page_size: 1 }),
      ).rejects.toBeTruthy();

      // "Consentimientos pendientes" + "Insights IA desactualizados"
      // comparten la única instancia de `useCoachSummary()` → ambas caen
      // juntas cuando ese agregado falla.
      mockUseCoachSummary.mockReturnValue({
        isLoading: false,
        isError: true,
        data: undefined,
        error: new Error("server"),
        refetch: vi.fn(),
      } as unknown as CoachSummaryQueryResult);
      // "Actividades sin enlazar" cae de forma independiente.
      mockUseActivityReview.mockReturnValue({
        isLoading: false,
        isError: true,
        data: undefined,
        error: new Error("server"),
        refetch: vi.fn(),
      } as unknown as ActivityQueryResult);

      renderInbox();

      // Las 3 filas afectadas se omiten por completo — nunca como línea
      // vacía, spinner eterno ni banner de error (FR-004).
      expect(screen.queryByText(LABELS.activities)).not.toBeInTheDocument();
      expect(screen.queryByText(LABELS.consents)).not.toBeInTheDocument();
      expect(screen.queryByText(LABELS.insights)).not.toBeInTheDocument();

      // Las filas restantes, con fuentes sanas, se mantienen visibles.
      expect(screen.getByText(LABELS.results)).toBeInTheDocument();
      expect(screen.getByText(LABELS.newsletters)).toBeInTheDocument();

      // Sin banner de error en ningún punto de la página (ni rol `alert`
      // ni el texto de reintento de `ErrorState`).
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(screen.queryByText(/reintentar/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
    });
  });
});
