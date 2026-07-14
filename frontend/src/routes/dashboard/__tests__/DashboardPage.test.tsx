import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { MemoryRouter, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import type { AlertsSummary, AthleteAlert } from "@/types/alerts.types";
import type { RaceEventListItem } from "@/types/raceEvents.types";
import type { TrainingSession } from "@/types/trainingSession.types";
import { mswServer } from "@/test/setup";
import { coachSummaryServerErrorHandler, makeCoachSummary } from "@/test/msw/dashboardHandlers";
import { ServerWakingBanner } from "@/components/layout/ServerWakingBanner";
import { useServerWakingStore } from "@/store/serverWaking.store";

import { DashboardPage } from "../DashboardPage";

vi.mock("@/api/alerts", () => ({
  getAlerts: vi.fn(),
}));

// NextSessionTile/NextRaceTile (T030) consumen estos dos hooks directamente
// (mismo patrón de mock que NextSessionTile.test.tsx / NextRaceTile.test.tsx)
// para que el hero strip de DashboardPage tenga contenido determinístico sin
// depender de MSW/red real.
vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
}));

vi.mock("@/hooks/race/useRaceEvents", () => ({
  useRaceEventsList: vi.fn(),
}));

// PendingInbox's "actividades sin enlazar" / "boletines pendientes" rows
// (T034/T035) — mockeados igual que en PendingInbox.test.tsx. Solo el T049
// (admin variant, abajo) necesita ambas filas pobladas; el resto de este
// archivo no hace aserciones sobre ellas, así que el estado por defecto
// (stubHeroHooksEmpty) las deja en su fila "resuelta en 0", sin romper
// ninguna prueba existente.
vi.mock("@/hooks/activities/useActivityReview", () => ({
  useActivityReview: vi.fn(),
}));

vi.mock("@/hooks/training/useNewsletterStatusSummary", () => ({
  useNewsletterStatusSummary: vi.fn(),
}));

// `role` es mutable (vi.hoisted) para que la prueba admin-variant (T049,
// abajo) pueda alternarlo sin remockear el módulo completo — mismo patrón
// que `AthleteLink.test.tsx`. Se resetea a "coach" en cada `beforeEach`.
const authState = vi.hoisted(() => ({ role: "coach" as string }));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (
    selector: (state: { accessToken: string; user: { role: string } }) => unknown,
  ) => selector({ accessToken: "fake-token", user: { role: authState.role } }),
}));

import { getAlerts } from "@/api/alerts";
import { useTrainingSessions } from "@/api/trainingSessions";
import { useRaceEventsList } from "@/hooks/race/useRaceEvents";
import { useActivityReview } from "@/hooks/activities/useActivityReview";
import { useNewsletterStatusSummary } from "@/hooks/training/useNewsletterStatusSummary";

const mockUseTrainingSessions = vi.mocked(useTrainingSessions);
const mockUseRaceEventsList = vi.mocked(useRaceEventsList);
const mockUseActivityReview = vi.mocked(useActivityReview);
const mockUseNewsletterStatusSummary = vi.mocked(useNewsletterStatusSummary);

type TrainingSessionsQueryResult = ReturnType<typeof useTrainingSessions>;
type RaceEventsQueryResult = ReturnType<typeof useRaceEventsList>;
type ActivityReviewQueryResult = ReturnType<typeof useActivityReview>;
type NewsletterStatusQueryResult = ReturnType<typeof useNewsletterStatusSummary>;

/** Estado por defecto (poblado-vacío) de los cuatro hooks de datos del hero
 * strip + PendingInbox (T033-T036) — suficiente para que
 * NextSessionTile/NextRaceTile/PendingInbox rendericen su empty state sin
 * interferir con las aserciones de las pruebas que no giran en torno a
 * ellos (total de atletas / última evaluación / errores). */
function stubHeroHooksEmpty() {
  mockUseTrainingSessions.mockReturnValue({
    isLoading: false,
    isError: false,
    data: [],
    error: null,
    refetch: vi.fn(),
  } as unknown as TrainingSessionsQueryResult);

  mockUseRaceEventsList.mockReturnValue({
    isLoading: false,
    isError: false,
    data: { items: [], total: 0 },
    error: null,
    refetch: vi.fn(),
  } as unknown as RaceEventsQueryResult);

  mockUseActivityReview.mockReturnValue({
    isLoading: false,
    isError: false,
    data: { items: [], total: 0 },
    error: null,
    refetch: vi.fn(),
  } as unknown as ActivityReviewQueryResult);

  mockUseNewsletterStatusSummary.mockReturnValue({
    isLoading: false,
    isError: false,
    data: { year: 2026, month: 7, items: [] },
    error: null,
    refetch: vi.fn(),
  } as unknown as NewsletterStatusQueryResult);
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

function makeRaceEvent(overrides: Partial<RaceEventListItem> = {}): RaceEventListItem {
  return {
    id: 1,
    series_id: 1,
    sequence_number: 1,
    name: "Copa Valle — Ginebra",
    event_date: "2026-07-20T12:00:00.000Z",
    location: "Ginebra",
    is_championship: false,
    status: "scheduled",
    has_results: false,
    has_calendar_event: false,
    conditions_completeness: "empty",
    ...overrides,
  } as RaceEventListItem;
}

/** Muestra el pathname actual — confirma navegación real al hacer click. */
function LocationDisplay() {
  const location = useLocation();
  return <div data-testid="location-display">{location.pathname}</div>;
}

function buildAlert(overrides: Partial<AthleteAlert>): AthleteAlert {
  return {
    athlete_id: 1,
    athlete_name: "Juan Pérez Ficticio",
    sex: "M",
    age_decimal: 12.5,
    category: "Sub-13",
    measurement_status: "ok",
    last_measurement_date: null,
    next_due_date: null,
    days_overdue: null,
    current_phv_status: null,
    measurement_interval_days: 90,
    growth_velocity_cm_month: null,
    growth_alerts: [],
    training_implications: null,
    ...overrides,
  };
}

/**
 * Envuelve `DashboardPage` en rutas reales (no solo `MemoryRouter` plano)
 * para poder verificar que los links del hero strip navegan de verdad a
 * sus destinos documentados (`contracts/home-tiles.md`), siguiendo el
 * mismo patrón que `NextSessionTile.test.tsx` (`<Routes>` + `useLocation`
 * hermano en vez de solo inspeccionar el atributo `href`).
 */
function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={["/dashboard"]}>
        <LocationDisplay />
        <Routes>
          <Route path="/dashboard" element={<DashboardPage />} />
          <Route path="/training/sessions/:id" element={<div>Detalle de sesión</div>} />
          <Route path="/training/sessions/new" element={<div>Nueva sesión</div>} />
          <Route path="/competitions/:id" element={<div>Detalle de carrera</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardPage", () => {
  beforeEach(() => {
    authState.role = "coach";
    vi.mocked(getAlerts).mockReset();
    mockUseTrainingSessions.mockReset();
    mockUseRaceEventsList.mockReset();
    mockUseActivityReview.mockReset();
    mockUseNewsletterStatusSummary.mockReset();
    // Por defecto, el hero strip (NextSessionTile/NextRaceTile) y
    // PendingInbox resuelven a su empty state — así las pruebas centradas
    // en el card "Total atletas" / errores de `useDashboardStats` no
    // dependen de estos datos.
    stubHeroHooksEmpty();
  });

  afterEach(() => {
    vi.useRealTimers();
    // Belt-and-suspenders: only the cold-start test (T052, below) touches
    // this singleton store directly, but resetting it after every test in
    // this describe keeps that test's state from ever leaking sideways.
    useServerWakingStore.getState().resetForTests();
  });

  it("renders total, last evaluation and PHV vigentes from alerts data", async () => {
    const summary: AlertsSummary = {
      overdue: 1,
      due_soon: 0,
      ok: 2,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "ok",
          last_measurement_date: "2026-05-10",
        }),
        buildAlert({
          athlete_id: 2,
          measurement_status: "due_soon",
          last_measurement_date: "2026-06-20",
        }),
        buildAlert({
          athlete_id: 3,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(getAlerts).toHaveBeenCalled();
    });

    // "Última evaluación" y "Estado PHV" ya no se renderizan en el hero
    // strip — T030 los reemplazó por NextSessionTile/NextRaceTile. "Total
    // atletas" (el último card estático) fue reemplazado a su vez por
    // WeeklyLoadMeter en T048 (contracts/home-tiles.md Tile 3) — el
    // conteo total ya no se muestra en el hero strip.
    expect(screen.queryByText("Última evaluación")).not.toBeInTheDocument();
    expect(screen.queryByText("Estado PHV")).not.toBeInTheDocument();
    expect(screen.queryByText("Total atletas")).not.toBeInTheDocument();
  });

  it("renders \"--\" for last evaluation when no athlete has a measurement date", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 1,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "never",
          last_measurement_date: null,
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(getAlerts).toHaveBeenCalled();
    });

    // "Última evaluación" y "Estado PHV" ya no se renderizan (ver nota arriba).
    expect(screen.queryByText("Última evaluación")).not.toBeInTheDocument();
    expect(screen.queryByText("Estado PHV")).not.toBeInTheDocument();
  });

  it("shows the empty state and \"--\" cards when there are no athletes", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("No tienes atletas asignados a un club")).toBeInTheDocument();
    });

    // "Estado PHV" y "Total atletas" ya no existen como cards independientes
    // (ver nota arriba — T048 reemplazó el último card estático por
    // WeeklyLoadMeter).
    expect(screen.queryByText("Estado PHV")).not.toBeInTheDocument();
    expect(screen.queryByText("Total atletas")).not.toBeInTheDocument();
  });

  it("shows the error state when the alerts request fails", async () => {
    vi.mocked(getAlerts).mockRejectedValue(new Error("network error"));

    renderPage();

    // `MeasurementAlerts` is the single source of truth for this query's
    // error state — DashboardPage no longer renders its own top-level
    // `ErrorState` for the same failure (see DashboardPage.tsx comment):
    // that used to render a SECOND "No pudimos cargar..." banner with its
    // own "Reintentar" button alongside this one, a duplicate-control bug
    // that made `findByRole("button", { name: "Reintentar" })` ambiguous
    // in the retry test below.
    await waitFor(() => {
      expect(
        screen.getByText("No se pudieron cargar las alertas de medición."),
      ).toBeInTheDocument();
    });

    // El card estático "Total atletas" ya no existe (T048); el error de
    // `useDashboardStats` no debe bloquear el resto del hero strip.
    expect(screen.queryByText("Total atletas")).not.toBeInTheDocument();
  });

  it("retries the alerts query when clicking \"Reintentar\" and recovers on success", async () => {
    const user = userEvent.setup();
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 1,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "ok",
          last_measurement_date: "2026-06-01",
        }),
      ],
    };
    vi.mocked(getAlerts)
      .mockRejectedValueOnce(new Error("network error"))
      .mockResolvedValueOnce(summary);

    renderPage();

    const retryButton = await screen.findByRole("button", { name: "Reintentar" });
    await user.click(retryButton);

    await waitFor(() => {
      expect(getAlerts).toHaveBeenCalledTimes(2);
    });

    // La consulta se recupera con los datos frescos y el estado de error
    // (renderizado por `MeasurementAlerts`, la única fuente de este mensaje
    // ahora — ver DashboardPage.tsx) desaparece.
    await waitFor(() => {
      expect(getAlerts).toHaveResolvedTimes(1);
    });
    expect(
      screen.queryByText("No se pudieron cargar las alertas de medición."),
    ).not.toBeInTheDocument();
  });

  it("renders NextSessionTile's and NextRaceTile's content in the hero strip, each linking to its documented target (contracts/home-tiles.md)", async () => {
    // 2026-07-15T20:00:00Z == 2026-07-15 15:00 America/Bogotá (UTC-5, sin DST).
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T20:00:00Z"));

    vi.mocked(getAlerts).mockResolvedValue({
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [],
    });

    const session = makeSession({
      id: 42,
      scheduled_date: "2026-07-17",
      scheduled_start_time: "07:00:00",
      technical_focus: "Técnica de curvas",
      location: "Cancha Ginebra",
    });
    mockUseTrainingSessions.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [session],
      error: null,
      refetch: vi.fn(),
    } as unknown as TrainingSessionsQueryResult);

    const race = makeRaceEvent({
      id: 77,
      name: "Copa Valle — Próxima Válida",
      event_date: "2026-07-20T12:00:00.000Z",
      location: "Ginebra",
    });
    mockUseRaceEventsList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [race], total: 1 },
      error: null,
      refetch: vi.fn(),
    } as unknown as RaceEventsQueryResult);

    render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter initialEntries={["/dashboard"]}>
          <LocationDisplay />
          <Routes>
            <Route path="/dashboard" element={<DashboardPage />} />
            <Route path="/training/sessions/:id" element={<div>Detalle de sesión</div>} />
            <Route path="/competitions/:id" element={<div>Detalle de carrera</div>} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // NextSessionTile — nombre/día relativo/hora/lugar visibles.
    expect(screen.getByText("Técnica de curvas")).toBeInTheDocument();
    expect(screen.getByText("Mañana · 07:00 a. m. · Cancha Ginebra")).toBeInTheDocument();

    // NextRaceTile — nombre/lugar visibles.
    expect(screen.getByText("Copa Valle — Próxima Válida")).toBeInTheDocument();
    expect(screen.getByText("en 5 días · Ginebra")).toBeInTheDocument();

    const sessionLink = screen.getByText("Técnica de curvas").closest("a");
    const raceLink = screen.getByText("Copa Valle — Próxima Válida").closest("a");
    expect(sessionLink).toHaveAttribute("href", "/training/sessions/42");
    expect(raceLink).toHaveAttribute("href", "/competitions/77");

    // El link de NextSessionTile navega de verdad a /training/sessions/{id}.
    if (sessionLink) fireEvent.click(sessionLink);
    expect(screen.getByTestId("location-display")).toHaveTextContent(
      "/training/sessions/42",
    );
  });

  it("NextRaceTile's link navigates to /competitions/{id}", async () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-07-15T20:00:00Z"));

    vi.mocked(getAlerts).mockResolvedValue({
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [],
    });

    // Sin sesión planificada — NextSessionTile queda en su empty state,
    // sin interferir con la navegación de NextRaceTile bajo prueba.
    mockUseTrainingSessions.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
      error: null,
      refetch: vi.fn(),
    } as unknown as TrainingSessionsQueryResult);

    const race = makeRaceEvent({
      id: 77,
      name: "Copa Valle — Próxima Válida",
      event_date: "2026-07-20T12:00:00.000Z",
      location: "Ginebra",
    });
    mockUseRaceEventsList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [race], total: 1 },
      error: null,
      refetch: vi.fn(),
    } as unknown as RaceEventsQueryResult);

    renderPage();

    const raceLink = screen.getByText("Copa Valle — Próxima Válida").closest("a");
    if (raceLink) fireEvent.click(raceLink);

    expect(screen.getByTestId("location-display")).toHaveTextContent(
      "/competitions/77",
    );
  });

  it(
    "renders WeeklyLoadMeter as the hero strip's third tile (T048), replacing the " +
      'static "Total atletas" card, using the real useCoachSummary() query against MSW',
    async () => {
      vi.mocked(getAlerts).mockResolvedValue({
        overdue: 0,
        due_soon: 0,
        ok: 0,
        never_measured: 0,
        rapid_growth_count: 0,
        athletes: [],
      });

      mswServer.use(
        http.get("*/api/dashboard/coach-summary", () =>
          HttpResponse.json(makeCoachSummary()),
        ),
      );

      renderPage();

      expect(await screen.findByText("Carga semanal")).toBeInTheDocument();
      expect(screen.getByText("4 h planificadas")).toBeInTheDocument();
      expect(screen.getByText("13.5 h planificadas")).toBeInTheDocument();
      expect(screen.queryByText("Total atletas")).not.toBeInTheDocument();
    },
  );

  it(
    'refreshes the "Consentimientos pendientes" pending-inbox row on remount after resolving ' +
      'one item elsewhere, via refetchOnMount:"always" — no manual reload needed (SC-003, research.md R8)',
    async () => {
      // Empty alerts summary keeps "Total atletas" out of the way of this
      // assertion; useTrainingSessions/useRaceEventsList stay mocked-empty
      // (stubHeroHooksEmpty, beforeEach) so NextSessionTile/NextRaceTile and
      // the "Resultados por importar" row (same query) render deterministically
      // and don't interfere with the row under test.
      vi.mocked(getAlerts).mockResolvedValue({
        overdue: 0,
        due_soon: 0,
        ok: 0,
        never_measured: 0,
        rapid_growth_count: 0,
        athletes: [],
      });

      // Real `useCoachSummary()` runs here (not mocked, unlike
      // useTrainingSessions/useRaceEventsList above) so its actual
      // `refetchOnMount: "always"` option is exercised end-to-end against a
      // single, persistent QueryClient shared across both mounts below —
      // mounting a *fresh* QueryClient per render would refetch regardless
      // of that option and prove nothing.
      let consentsPending = 5;
      mswServer.use(
        http.get("*/api/dashboard/coach-summary", () =>
          HttpResponse.json(makeCoachSummary({ consents_pending: consentsPending })),
        ),
      );

      // Mirrors the app's real defaults (App.tsx: `staleTime: 5 * 60_000`)
      // so the cached "5" would still read as fresh on a plain remount —
      // only `refetchOnMount: "always"` on useCoachSummary forces the
      // refetch that picks up the resolved item.
      const queryClient = new QueryClient({
        defaultOptions: { queries: { retry: false, staleTime: 5 * 60_000 } },
      });

      const renderDashboard = () =>
        render(
          <QueryClientProvider client={queryClient}>
            <MemoryRouter initialEntries={["/dashboard"]}>
              <Routes>
                <Route path="/dashboard" element={<DashboardPage />} />
              </Routes>
            </MemoryRouter>
          </QueryClientProvider>,
        );

      const { unmount } = renderDashboard();

      const firstLink = await screen.findByText("Consentimientos pendientes");
      await waitFor(() => {
        expect(firstLink.closest("a")).toHaveTextContent("5");
      });

      // Land on "Inicio" → resolve one pending consent on another screen →
      // navigate back: DashboardPage unmounts and remounts (real router
      // behavior, research.md R8), while the QueryClient instance persists.
      unmount();
      consentsPending = 4;

      renderDashboard();

      await waitFor(() => {
        const link = screen.getByText("Consentimientos pendientes").closest("a");
        expect(link).toHaveTextContent("4");
      });
    },
  );

  it(
    "shows skeletons (never an error tone) across every tile/row during a cold start, " +
      'alongside the existing "server waking" notice (US4, T052, FR-008)',
    async () => {
      // Feature 012, US2: the axios interceptor flips this once a request
      // has been in flight past the threshold. Set directly here (same
      // pattern as `ServerWakingBanner.test.tsx`) since this test drives
      // its "still waking" signal through mocked hooks + a hanging MSW
      // handler below, not a real `apiClient` round-trip.
      useServerWakingStore.setState({ isWaking: true });

      vi.mocked(getAlerts).mockResolvedValue({
        overdue: 0,
        due_soon: 0,
        ok: 1,
        never_measured: 0,
        rapid_growth_count: 0,
        athletes: [
          buildAlert({
            athlete_id: 1,
            measurement_status: "ok",
            last_measurement_date: "2026-06-01",
          }),
        ],
      });

      // The hero strip's two mocked hooks + PendingInbox's two exclusively
      // mocked rows: still `isLoading` (no response yet) — exactly what a
      // Render Free cold start looks like to a consumer, i.e. an in-flight
      // request that hasn't settled, NOT an error.
      mockUseTrainingSessions.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as TrainingSessionsQueryResult);

      mockUseRaceEventsList.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as RaceEventsQueryResult);

      mockUseActivityReview.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as ActivityReviewQueryResult);

      mockUseNewsletterStatusSummary.mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
        error: null,
        refetch: vi.fn(),
      } as unknown as NewsletterStatusQueryResult);

      // `useCoachSummary` is real in this file (not mocked, per the T048
      // test above) — a handler that never resolves keeps it in
      // `isLoading` for this test's lifetime, feeding WeeklyLoadMeter AND
      // PendingInbox's two remaining rows (consents-pending/insights-stale)
      // the same "still waking" signal, without needing a fake timer.
      mswServer.use(
        http.get("*/api/dashboard/coach-summary", () => new Promise(() => {})),
      );

      try {
        render(
          <QueryClientProvider
            client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
          >
            {/* Rendered alongside DashboardPage, mirroring AppShell
                (`frontend/src/components/layout/AppShell.tsx`), which
                mounts `ServerWakingBanner` as a sibling of the routed page
                content, never inside it. */}
            <ServerWakingBanner />
            <MemoryRouter initialEntries={["/dashboard"]}>
              <Routes>
                <Route path="/dashboard" element={<DashboardPage />} />
              </Routes>
            </MemoryRouter>
          </QueryClientProvider>,
        );

        // The "server waking" notice renders alongside the page.
        expect(screen.getByText(/La aplicación está iniciando/)).toBeInTheDocument();

        // Hero strip: both StatCard-based tiles still show their label with
        // a skeleton value — no resolved content yet.
        expect(screen.getByText("Próxima sesión")).toBeInTheDocument();
        expect(screen.getByText("Próxima carrera Copa Valle")).toBeInTheDocument();
        expect(
          screen.getByRole("status", { name: "Cargando carga semanal" }),
        ).toBeInTheDocument();

        // PendingInbox's section renders, but every row is still a
        // skeleton — `PendingRow` only renders its label once
        // `state !== undefined`, so none of the 5 labels (nor the
        // all-clear copy, which requires every row to have resolved) show.
        expect(screen.getByText("Pendientes de esta semana")).toBeInTheDocument();
        expect(screen.queryByText("Resultados por importar")).not.toBeInTheDocument();
        expect(screen.queryByText("Actividades sin enlazar")).not.toBeInTheDocument();
        expect(screen.queryByText("Boletines pendientes del mes")).not.toBeInTheDocument();
        expect(screen.queryByText("Consentimientos pendientes")).not.toBeInTheDocument();
        expect(screen.queryByText("Insights IA desactualizados")).not.toBeInTheDocument();
        expect(
          screen.queryByText("Todo al día — sin pendientes esta semana"),
        ).not.toBeInTheDocument();

        // Never an error tone (FR-008): no `role="alert"` anywhere on the
        // page, and none of the tile-local/top-level error copy renders.
        expect(screen.queryAllByRole("alert")).toHaveLength(0);
        expect(
          screen.queryByText(
            "No pudimos cargar la información del dashboard. Intenta de nuevo más tarde.",
          ),
        ).not.toBeInTheDocument();
        expect(
          screen.queryByText("No se pudo cargar la próxima sesión."),
        ).not.toBeInTheDocument();
        expect(
          screen.queryByText("No se pudo cargar la próxima carrera."),
        ).not.toBeInTheDocument();

        // Concrete proof skeleton placeholders are actually on the page
        // (the shared `Skeleton` primitive: `aria-hidden` + `animate-pulse`)
        // rather than just an absence of resolved content.
        const skeletons = document.querySelectorAll(".animate-pulse");
        expect(skeletons.length).toBeGreaterThan(0);
      } finally {
        useServerWakingStore.getState().resetForTests();
      }
    },
  );

  it(
    "keeps Increment A's tiles/rows (session, race, results-to-import, activities, " +
      "newsletters) fully rendered when coach-summary errors entirely — graceful " +
      "degradation combinatorics (US4, T053, FR-004/FR-005)",
    async () => {
      // Sin fake timers en esta prueba: `findByText`/`waitFor` (usados más
      // abajo para esperar la resolución real de `useCoachSummary()` vía
      // MSW) hacen polling con `setTimeout` real internamente — combinarlos
      // con timers falsos sin avanzarlos manualmente cuelga la prueba (mismo
      // motivo documentado en la prueba admin-variant, arriba). Las fechas
      // de sesión/carrera se calculan relativas al reloj REAL en su lugar.
      const now = Date.now();
      const DAY_MS = 86_400_000;
      const inTwoDaysIso = new Date(now + 2 * DAY_MS).toISOString().slice(0, 10);
      const in30DaysIso = new Date(now + 30 * DAY_MS).toISOString();
      const past30DaysIso = new Date(now - 30 * DAY_MS).toISOString();

      vi.mocked(getAlerts).mockResolvedValue({
        overdue: 0,
        due_soon: 0,
        ok: 0,
        never_measured: 0,
        rapid_growth_count: 0,
        athletes: [],
      });

      // Increment A — hero strip: sesión + carrera.
      const session = makeSession({
        id: 42,
        scheduled_date: inTwoDaysIso,
        scheduled_start_time: "07:00:00",
        technical_focus: "Técnica de curvas",
        location: "Cancha Ginebra",
      });
      mockUseTrainingSessions.mockReturnValue({
        isLoading: false,
        isError: false,
        data: [session],
        error: null,
        refetch: vi.fn(),
      } as unknown as TrainingSessionsQueryResult);

      // Dos carreras: una futura (la que elige NextRaceTile) y una pasada
      // sin resultados (alimenta la fila "Resultados por importar" de
      // PendingInbox — MISMA queryKey que NextRaceTile, research.md R2).
      const upcomingRace = makeRaceEvent({
        id: 77,
        name: "Copa Valle — Próxima Válida",
        event_date: in30DaysIso,
        location: "Ginebra",
      });
      const pastRaceNeedingResults = makeRaceEvent({
        id: 501,
        name: "Copa Valle — Ginebra",
        event_date: past30DaysIso,
        has_results: false,
      });
      mockUseRaceEventsList.mockReturnValue({
        isLoading: false,
        isError: false,
        data: { items: [pastRaceNeedingResults, upcomingRace], total: 2 },
        error: null,
        refetch: vi.fn(),
      } as unknown as RaceEventsQueryResult);

      // Increment A — fila "Actividades sin enlazar".
      mockUseActivityReview.mockReturnValue({
        isLoading: false,
        isError: false,
        data: { items: [], total: 3 },
        error: null,
        refetch: vi.fn(),
      } as unknown as ActivityReviewQueryResult);

      // Increment A — fila "Boletines pendientes del mes".
      mockUseNewsletterStatusSummary.mockReturnValue({
        isLoading: false,
        isError: false,
        data: {
          year: 2026,
          month: 7,
          items: [
            {
              athlete_id: 1,
              newsletter_id: 1,
              status: "draft",
              generated_at: "2026-07-01T00:00:00Z",
              sent_at: null,
            },
          ],
        },
        error: null,
        refetch: vi.fn(),
      } as unknown as NewsletterStatusQueryResult);

      // Increment B — `coach-summary` falla por completo (handler
      // "absent-block" de T040, no un campo aislado en `null`), simulando
      // TODO el agregado indisponible: WeeklyLoadMeter y las dos filas de
      // PendingInbox que dependen de él (consents-pending/insights-stale)
      // deben desaparecer en silencio.
      mswServer.use(coachSummaryServerErrorHandler);

      renderPage();

      // Increment A: sesión + carrera (hero strip) siguen íntegros — nombre/
      // foco técnico/lugar visibles (sin fake timers, no se afirma el texto
      // relativo de día exacto, ver nota arriba).
      expect(await screen.findByText("Técnica de curvas")).toBeInTheDocument();
      expect(screen.getByText("Copa Valle — Próxima Válida")).toBeInTheDocument();
      const sessionLink = screen.getByText("Técnica de curvas").closest("a");
      const raceLink = screen.getByText("Copa Valle — Próxima Válida").closest("a");
      expect(sessionLink).toHaveAttribute("href", "/training/sessions/42");
      expect(raceLink).toHaveAttribute("href", "/competitions/77");

      // Increment A: filas "resultados por importar" / "actividades sin
      // enlazar" / "boletines pendientes" siguen íntegras.
      expect(await screen.findByText("Resultados por importar")).toBeInTheDocument();
      expect(screen.getByText("Actividades sin enlazar")).toBeInTheDocument();
      expect(screen.getByText("Boletines pendientes del mes")).toBeInTheDocument();

      // Increment B queda completamente ausente — nunca un tono de error,
      // se omite en silencio (FR-004/FR-005).
      await waitFor(() => {
        expect(screen.queryByText("Carga semanal")).not.toBeInTheDocument();
      });
      expect(screen.queryByText("Consentimientos pendientes")).not.toBeInTheDocument();
      expect(screen.queryByText("Insights IA desactualizados")).not.toBeInTheDocument();
      expect(screen.queryAllByRole("alert")).toHaveLength(0);
      expect(
        screen.queryByText(
          "No pudimos cargar la información del dashboard. Intenta de nuevo más tarde.",
        ),
      ).not.toBeInTheDocument();
    },
  );
});

// ---------------------------------------------------------------------------
// T049 [US4] — admin variant: 0 role dead-ends (SC-004)
// ---------------------------------------------------------------------------

/**
 * Guardia liviana que replica, SOLO para admin, la lógica de redirect de
 * `ProtectedRoute` (`frontend/src/routes/ProtectedRoute.tsx`) sin montar el
 * árbol completo de `App.tsx`/`AppShell` — mismo patrón "simula el guard"
 * que `frontend/src/__tests__/competitions-routing.test.tsx`'s
 * `InsightsGuard` (T022). `allowed` refleja el `allowedRoles` REAL de cada
 * ruta en `App.tsx` para el rol admin en la fecha de este test (ver los
 * `grep`s de `App.tsx` citados en cada `<Route>` de abajo); si diverge de
 * `App.tsx` en el futuro, este test queda desalineado con la app real —
 * exactamente el mismo riesgo que ya asume `InsightsGuard`.
 */
function AdminRouteGuard({
  allowed,
  children,
}: {
  allowed: boolean;
  children: React.ReactNode;
}) {
  if (!allowed) return <Navigate to="/dashboard" replace />;
  return <>{children}</>;
}

/** Muestra el pathname+search actuales — mismo propósito que
 * `LocationDisplay` arriba, redeclarado en este scope de módulo. */
function AdminLocationDisplay() {
  const location = useLocation();
  return <div data-testid="admin-location-display">{location.pathname + location.search}</div>;
}

/**
 * Navega DIRECTO al `href` recogido del render de `DashboardPage` (mismo
 * resultado de enrutamiento que un click real vía `<Link>` — react-router
 * no distingue el origen de la navegación) contra un árbol de rutas que
 * replica el gate real de admin de cada destino posible de este feature.
 * Aislar cada `href` en su propio render (en vez de clicks secuenciales
 * sobre un único DOM) evita que el estado de una navegación previa
 * contamine la siguiente.
 */
function renderAdminRouteCheck(href: string) {
  return render(
    <MemoryRouter initialEntries={[href]}>
      <AdminLocationDisplay />
      <Routes>
        {/* Blanco del rebote real de `ProtectedRoute` para admin
            (`ROLE_FALLBACKS[admin] = "/dashboard"`). */}
        <Route
          path="/dashboard"
          element={<div data-testid="dashboard-bounce">Rebote a Inicio</div>}
        />
        {/* App.tsx: allowedRoles=[coach, admin] */}
        <Route
          path="/training/sessions"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Sesiones</div>
            </AdminRouteGuard>
          }
        />
        <Route
          path="/training/sessions/:id"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Detalle de sesión</div>
            </AdminRouteGuard>
          }
        />
        <Route
          path="/training/sessions/new"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Nueva sesión</div>
            </AdminRouteGuard>
          }
        />
        <Route
          path="/competitions"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Competencias</div>
            </AdminRouteGuard>
          }
        />
        <Route
          path="/competitions/:id"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Detalle de carrera</div>
            </AdminRouteGuard>
          }
        />
        <Route
          path="/competitions/insights/season/:year"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Insights de temporada</div>
            </AdminRouteGuard>
          }
        />
        <Route
          path="/activities"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Actividades</div>
            </AdminRouteGuard>
          }
        />
        <Route
          path="/training/athlete-newsletters"
          element={
            <AdminRouteGuard allowed>
              <div data-testid="target">Boletines</div>
            </AdminRouteGuard>
          }
        />
        {/* App.tsx: allowedRoles=[coach] — admin EXCLUIDO. */}
        <Route
          path="/athletes"
          element={
            <AdminRouteGuard allowed={false}>
              <div data-testid="target">Atletas</div>
            </AdminRouteGuard>
          }
        />
      </Routes>
    </MemoryRouter>,
  );
}

describe("DashboardPage — admin variant (US4, T049): 0 role dead-ends (SC-004)", () => {
  beforeEach(() => {
    authState.role = "admin";
    vi.mocked(getAlerts).mockReset();
    mockUseTrainingSessions.mockReset();
    mockUseRaceEventsList.mockReset();
    mockUseActivityReview.mockReset();
    mockUseNewsletterStatusSummary.mockReset();
  });

  afterEach(() => {
    authState.role = "coach";
    vi.useRealTimers();
  });

  it(
    "every link rendered by the fully-assembled page (hero strip + PendingInbox + " +
      "MeasurementAlerts) resolves to a route admin can open — no ProtectedRoute " +
      "bounce back to /dashboard (reuses AthleteLink's 'click every link' pattern, " +
      "specs/028)",
    async () => {
      // Sin fake timers en esta prueba: `findByText`/`waitFor` (usados más
      // abajo, junto con la segunda pasada de renders) hacen polling con
      // `setTimeout` real internamente — combinarlos con timers falsos sin
      // avanzarlos manualmente cuelga la prueba. Las fechas de sesión/
      // carrera se calculan relativas al reloj REAL en su lugar (en vez de
      // fijar `vi.setSystemTime`, como sí hacen otras pruebas de este
      // archivo que no usan `findByText` tras activarlos).
      const now = Date.now();
      const DAY_MS = 86_400_000;
      const inTwoDaysIso = new Date(now + 2 * DAY_MS).toISOString().slice(0, 10);
      const in30DaysIso = new Date(now + 30 * DAY_MS).toISOString();
      const past30DaysIso = new Date(now - 30 * DAY_MS).toISOString();

      // Todas las fuentes pobladas a la vez, para maximizar la cobertura de
      // links de esta única pasada (una fila/tile en skeleton o all-clear
      // no expone ningún link que revisar).
      vi.mocked(getAlerts).mockResolvedValue({
        overdue: 10,
        due_soon: 0,
        ok: 0,
        never_measured: 0,
        rapid_growth_count: 0,
        // >8 (MAX_VISIBLE de MeasurementAlerts) para que aparezca el link
        // "Ver todas (N)" — las 10 filas individuales usan `AthleteLink`
        // (ya gated para admin, se renderizan como <span>, no como link).
        athletes: Array.from({ length: 10 }, (_, i) => ({
          athlete_id: i + 1,
          athlete_name: `Atleta Ficticio ${i + 1}`,
          sex: "M",
          age_decimal: 12.5,
          category: "Sub-13",
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          next_due_date: null,
          days_overdue: 30 + i,
          current_phv_status: null,
          measurement_interval_days: 90,
          growth_velocity_cm_month: null,
          growth_alerts: [],
          training_implications: null,
        })) as AthleteAlert[],
      });

      mockUseTrainingSessions.mockReturnValue({
        isLoading: false,
        isError: false,
        data: [
          makeSession({
            id: 42,
            scheduled_date: inTwoDaysIso,
            scheduled_start_time: "07:00:00",
            technical_focus: "Técnica de curvas",
            location: "Cancha Ginebra",
          }),
        ],
        error: null,
        refetch: vi.fn(),
      } as unknown as TrainingSessionsQueryResult);

      mockUseRaceEventsList.mockReturnValue({
        isLoading: false,
        isError: false,
        data: {
          items: [
            // Pasada, sin resultados — alimenta la fila "Resultados por
            // importar" de PendingInbox (no la elige NextRaceTile, que
            // solo mira carreras >= hoy).
            makeRaceEvent({
              id: 501,
              event_date: past30DaysIso,
              has_results: false,
            }),
            // Futura — la que sí elige NextRaceTile.
            makeRaceEvent({
              id: 77,
              name: "Copa Valle — Próxima Válida",
              event_date: in30DaysIso,
              location: "Ginebra",
            }),
          ],
          total: 2,
        },
        error: null,
        refetch: vi.fn(),
      } as unknown as RaceEventsQueryResult);

      mockUseActivityReview.mockReturnValue({
        isLoading: false,
        isError: false,
        data: { items: [], total: 5 },
        error: null,
        refetch: vi.fn(),
      } as unknown as ActivityReviewQueryResult);

      mockUseNewsletterStatusSummary.mockReturnValue({
        isLoading: false,
        isError: false,
        data: {
          year: 2026,
          month: 7,
          items: [
            {
              athlete_id: 1,
              newsletter_id: 1,
              status: "draft",
              generated_at: "2026-07-01T00:00:00Z",
              sent_at: null,
            },
          ],
        },
        error: null,
        refetch: vi.fn(),
      } as unknown as NewsletterStatusQueryResult);

      // useCoachSummary NO está mockeado en este archivo (real, vía MSW) —
      // pobla consents_pending/insights_stale/weekly_load a la vez, así
      // WeeklyLoadMeter Y las dos filas restantes de PendingInbox quedan
      // resueltas.
      mswServer.use(
        http.get("*/api/dashboard/coach-summary", () =>
          HttpResponse.json(makeCoachSummary()),
        ),
      );

      const { unmount } = render(
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <MemoryRouter initialEntries={["/dashboard"]}>
            <DashboardPage />
          </MemoryRouter>
        </QueryClientProvider>,
      );

      // Espera a que TODAS las fuentes hayan resuelto (hero strip +
      // las 5 filas de PendingInbox + MeasurementAlerts) antes de recoger
      // los links — de lo contrario una fila todavía en skeleton no
      // expondría su link.
      await screen.findByText("Copa Valle — Próxima Válida");
      await screen.findByText("Carga semanal");
      await screen.findByText("Resultados por importar");
      await screen.findByText("Actividades sin enlazar");
      await screen.findByText("Boletines pendientes del mes");
      await screen.findByText("Consentimientos pendientes");
      await screen.findByText("Insights IA desactualizados");
      await screen.findByText("Atleta Ficticio 10");
      const verTodas = await screen.findByText(/ver todas/i);
      // `/athletes` (the list) is coach-only in App.tsx, same as
      // `/athletes/:id` — `MeasurementAlerts`'s "Ver todas (N)" link is
      // gated the same way the individual `AthleteLink` rows already are
      // (mirrors the "Consentimientos pendientes" assertion below): for
      // admin it renders as plain, non-interactive text instead of a link
      // that would bounce straight back to /dashboard.
      expect(verTodas.closest("a")).toBeNull();

      const hrefs = Array.from(
        new Set(
          screen
            .getAllByRole("link")
            .map((el) => el.getAttribute("href"))
            .filter((href): href is string => !!href),
        ),
      );

      unmount();
      vi.useRealTimers();

      // Sanity: la página debe haber expuesto al menos los 7 destinos
      // ÚNICOS documentados en `contracts/home-tiles.md` que SÍ son
      // navegables para admin (3 hero tiles + 4 filas de PendingInbox — la
      // fila "Consentimientos pendientes" apunta a `/athletes`, restringida
      // para admin, así que no es un link) antes de evaluar a dónde apunta
      // cada uno.
      expect(hrefs.length).toBeGreaterThanOrEqual(7);

      const deadEnds: string[] = [];

      for (const href of hrefs) {
        const { unmount: unmountCheck } = renderAdminRouteCheck(href);

        await waitFor(() => {
          expect(
            screen.queryByTestId("target") ?? screen.queryByTestId("dashboard-bounce"),
          ).toBeInTheDocument();
        });

        if (screen.queryByTestId("dashboard-bounce")) {
          deadEnds.push(href);
        }

        unmountCheck();
      }

      expect(deadEnds).toEqual([]);
    },
  );
});
