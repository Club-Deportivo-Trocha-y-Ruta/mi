import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, waitFor, screen } from "@testing-library/react";
import { axe, toHaveNoViolations } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";

import type { AlertsSummary, AthleteAlert } from "@/types/alerts.types";
import type { RaceEventListItem } from "@/types/raceEvents.types";
import type { TrainingSession } from "@/types/trainingSession.types";
import { ServerWakingBanner } from "@/components/layout/ServerWakingBanner";
import { useServerWakingStore } from "@/store/serverWaking.store";

import { DashboardPage } from "../DashboardPage";

expect.extend(toHaveNoViolations);

// ---------------------------------------------------------------------------
// Mocks — idénticos a DashboardPage.test.tsx (__tests__) para consistencia
// ---------------------------------------------------------------------------

vi.mock("@/api/alerts", () => ({
  getAlerts: vi.fn(),
}));

// NextSessionTile/NextRaceTile (T030), PendingInbox (T032-T036) y
// WeeklyLoadMeter (T048) consumen estos cinco hooks directamente — se
// mockean con datos determinísticos (en vez de dejar pasar sus fetches
// reales por MSW) para que las pruebas de axe no dependan de una request de
// red real colgándose en jsdom.
vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
}));

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

// `role` es mutable (vi.hoisted) para que la prueba de la variante admin
// (T055, abajo) pueda alternarlo sin remockear el módulo completo — mismo
// patrón que `DashboardPage.test.tsx` (T049) / `AthleteLink.test.tsx`. Se
// resetea a "coach" en cada `beforeEach`.
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
import { useCoachSummary } from "@/hooks/dashboard/useCoachSummary";

const mockUseTrainingSessions = vi.mocked(useTrainingSessions);
const mockUseRaceEventsList = vi.mocked(useRaceEventsList);
const mockUseActivityReview = vi.mocked(useActivityReview);
const mockUseNewsletterStatusSummary = vi.mocked(useNewsletterStatusSummary);
const mockUseCoachSummary = vi.mocked(useCoachSummary);

type TrainingSessionsQueryResult = ReturnType<typeof useTrainingSessions>;
type RaceEventsQueryResult = ReturnType<typeof useRaceEventsList>;
type ActivityReviewQueryResult = ReturnType<typeof useActivityReview>;
type NewsletterStatusQueryResult = ReturnType<typeof useNewsletterStatusSummary>;
type CoachSummaryQueryResult = ReturnType<typeof useCoachSummary>;

/** Estado resuelto-vacío de los cinco hooks de datos del hero strip +
 * PendingInbox — determinístico, sin request de red real, para que las
 * pruebas de axe no dependan de un fetch colgado en jsdom (mismo patrón que
 * DashboardPage.test.tsx). */
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

  mockUseCoachSummary.mockReturnValue({
    isLoading: false,
    isError: false,
    data: {
      generated_at: "2026-07-11T20:03:00Z",
      consents_pending: null,
      insights_stale: null,
      weekly_load: null,
    },
    error: null,
    refetch: vi.fn(),
  } as unknown as CoachSummaryQueryResult);
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
    event_date: "2026-08-01T12:00:00.000Z",
    location: "Ginebra",
    is_championship: false,
    status: "scheduled",
    has_results: false,
    has_calendar_event: false,
    conditions_completeness: "empty",
    ...overrides,
  } as RaceEventListItem;
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

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("DashboardPage — accesibilidad WCAG 2.1 AA", () => {
  beforeEach(() => {
    vi.mocked(getAlerts).mockReset();
    mockUseTrainingSessions.mockReset();
    mockUseRaceEventsList.mockReset();
    mockUseActivityReview.mockReset();
    mockUseNewsletterStatusSummary.mockReset();
    mockUseCoachSummary.mockReset();
    stubHeroHooksEmpty();
  });

  it("no tiene violaciones en estado de carga (loading)", async () => {
    vi.mocked(getAlerts).mockReturnValue(new Promise(() => {})); // never resolves

    const { container } = renderPage();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones en estado listo (ready) con alertas mixtas", async () => {
    const summary: AlertsSummary = {
      overdue: 1,
      due_soon: 1,
      ok: 1,
      never_measured: 1,
      rapid_growth_count: 1,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30,
        }),
        buildAlert({
          athlete_id: 2,
          measurement_status: "due_soon",
          last_measurement_date: "2026-06-20",
          days_overdue: -5,
        }),
        buildAlert({
          athlete_id: 3,
          measurement_status: "ok",
          last_measurement_date: "2026-06-25",
        }),
        buildAlert({
          athlete_id: 4,
          athlete_name: "Ana Gómez Ficticia",
          measurement_status: "never",
          last_measurement_date: null,
        }),
        buildAlert({
          athlete_id: 5,
          athlete_name: "Luis Torres Ficticio",
          measurement_status: "ok",
          growth_alerts: ["rapid_growth"],
          growth_velocity_cm_month: 1.2,
          training_implications: "Ajustar carga de entrenamiento.",
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    const { container } = renderPage();

    await waitFor(() => {
      expect(getAlerts).toHaveBeenCalled();
    });
    await screen.findByText("Ana Gómez Ficticia");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones en estado vacío (empty)", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    const { container } = renderPage();

    await waitFor(() => {
      expect(
        screen.getByText("No tienes atletas asignados a un club"),
      ).toBeInTheDocument();
    });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("todos los enlaces son alcanzables por teclado (sin tabIndex negativo)", async () => {
    const summary: AlertsSummary = {
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: Array.from({ length: 10 }, (_, i) =>
        buildAlert({
          athlete_id: i + 1,
          athlete_name: `Atleta Ficticio ${i + 1}`,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30 + i,
        }),
      ),
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    // Ordenados por días de atraso descendente: "Atleta Ficticio 10" (el
    // más atrasado) siempre queda entre los primeros 8 mostrados.
    await waitFor(() => {
      expect(screen.getByText("Atleta Ficticio 10")).toBeInTheDocument();
    });

    // Con >8 atletas accionables se muestra el enlace "Ver todas (N)"
    const links = screen.getAllByRole("link");
    expect(links.length).toBeGreaterThan(0);
    for (const link of links) {
      expect(link).toHaveAttribute("href");
      expect(link.getAttribute("tabindex")).not.toBe("-1");
    }
    expect(screen.getByRole("link", { name: /ver todas/i })).toBeInTheDocument();
  });

  it("los enlaces de atletas cumplen el objetivo táctil mínimo de 44px (min-height del contenedor)", async () => {
    const summary: AlertsSummary = {
      overdue: 1,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30,
        }),
      ],
    };
    vi.mocked(getAlerts).mockResolvedValue(summary);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText("Juan Pérez Ficticio")).toBeInTheDocument();
    });

    // El <li> que envuelve el link de atleta usa px-4 py-3 (16px/12px) sobre
    // texto de 1.25rem de line-height efectivo, que junto al padding vertical
    // supera holgadamente los 44px de alto recomendados por WCAG 2.5.5.
    // Se documenta como recomendación (jsdom no calcula layout real) — ver
    // nota de UX abajo si se requiere medición runtime con getBoundingClientRect.
    const athleteLink = screen.getByRole("link", { name: "Juan Pérez Ficticio" });
    const row = athleteLink.closest("li");
    expect(row).not.toBeNull();
    expect(row?.className).toMatch(/py-3/);
  });
});

// ---------------------------------------------------------------------------
// T055 — jest-axe en las 5 estados requeridos del Inicio rediseñado
// (poblado, all-clear, degradado, cold-start/skeleton, variante admin),
// per `tasks.md` Phase 7. La suite anterior (arriba) ya cubre
// loading/ready/empty de `MeasurementAlerts` en aislamiento — este bloque
// ejercita la página COMPLETA (hero strip + PendingInbox + medidor de carga
// + MeasurementAlerts) ensamblada en T054, con cero violaciones exigidas en
// cada uno de los 5 estados (Constitution II).
// ---------------------------------------------------------------------------

describe("DashboardPage — accesibilidad WCAG 2.1 AA en los 5 estados de la página (T055)", () => {
  beforeEach(() => {
    authState.role = "coach";
    vi.mocked(getAlerts).mockReset();
    mockUseTrainingSessions.mockReset();
    mockUseRaceEventsList.mockReset();
    mockUseActivityReview.mockReset();
    mockUseNewsletterStatusSummary.mockReset();
    mockUseCoachSummary.mockReset();
  });

  afterEach(() => {
    authState.role = "coach";
    vi.useRealTimers();
    useServerWakingStore.getState().resetForTests();
  });

  it("no tiene violaciones en el estado poblado (hero strip + inbox + carga semanal + alertas mixtas)", async () => {
    // Sin fake timers: `findByText`/`waitFor` (usados abajo) hacen polling
    // con `setTimeout` real internamente — combinarlos con timers falsos sin
    // avanzarlos manualmente cuelga la prueba (mismo motivo documentado en
    // `DashboardPage.test.tsx`). Las fechas de sesión/carreras se calculan
    // relativas al reloj REAL en su lugar.
    const now = Date.now();
    const DAY_MS = 86_400_000;
    const inTwoDaysIso = new Date(now + 2 * DAY_MS).toISOString().slice(0, 10);
    const in10DaysIso = new Date(now + 10 * DAY_MS).toISOString();
    const past30DaysIso = new Date(now - 30 * DAY_MS).toISOString();

    vi.mocked(getAlerts).mockResolvedValue({
      overdue: 1,
      due_soon: 1,
      ok: 1,
      never_measured: 1,
      rapid_growth_count: 1,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30,
        }),
        buildAlert({
          athlete_id: 2,
          measurement_status: "due_soon",
          last_measurement_date: "2026-06-20",
          days_overdue: -5,
        }),
        buildAlert({
          athlete_id: 3,
          athlete_name: "Ana Gómez Ficticia",
          measurement_status: "never",
          last_measurement_date: null,
        }),
        buildAlert({
          athlete_id: 4,
          athlete_name: "Luis Torres Ficticio",
          measurement_status: "ok",
          growth_alerts: ["rapid_growth"],
          growth_velocity_cm_month: 1.2,
          training_implications: "Ajustar carga de entrenamiento.",
        }),
      ],
    });

    mockUseTrainingSessions.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [makeSession({ id: 42, scheduled_date: inTwoDaysIso })],
      error: null,
      refetch: vi.fn(),
    } as unknown as TrainingSessionsQueryResult);

    mockUseRaceEventsList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          // Pasada, sin resultados → alimenta "Resultados por importar".
          makeRaceEvent({ id: 501, event_date: past30DaysIso, has_results: false }),
          // Futura → la elige NextRaceTile.
          makeRaceEvent({ id: 77, name: "Copa Valle — Palmira", event_date: in10DaysIso }),
        ],
        total: 2,
      },
      error: null,
      refetch: vi.fn(),
    } as unknown as RaceEventsQueryResult);

    mockUseActivityReview.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 4 },
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
          { athlete_id: 1, newsletter_id: 1, status: "draft", generated_at: "2026-07-01T00:00:00Z", sent_at: null },
          { athlete_id: 2, newsletter_id: 2, status: "sent", generated_at: "2026-07-01T00:00:00Z", sent_at: "2026-07-02T00:00:00Z" },
        ],
      },
      error: null,
      refetch: vi.fn(),
    } as unknown as NewsletterStatusQueryResult);

    // weekly_load con una banda cómoda y otra sobre-tope (`over_cap`), para
    // ejercitar la barra a ancho completo + copy asesor de WeeklyLoadMeter.
    mockUseCoachSummary.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        generated_at: "2026-07-26T20:00:00Z",
        consents_pending: 3,
        insights_stale: 1,
        weekly_load: [
          { age_band: "10-12", planned_minutes: 240, cap_minutes: 600, athlete_count: 8 },
          { age_band: "13-15", planned_minutes: 810, cap_minutes: 780, athlete_count: 6 },
        ],
      },
      error: null,
      refetch: vi.fn(),
    } as unknown as CoachSummaryQueryResult);

    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Ana Gómez Ficticia");
    await screen.findByText("Copa Valle — Palmira");
    await screen.findByText("Resultados por importar");
    await screen.findByText("Carga semanal");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('no tiene violaciones en el estado "todo al día" (all-clear del inbox + tiles/alertas vacíos)', async () => {
    vi.mocked(getAlerts).mockResolvedValue({
      overdue: 0,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [],
    });

    // Hero strip en su estado vacío (sin sesión/carrera planificada).
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

    // Las 5 fuentes del inbox resuelven en 0 → estado "Todo al día".
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

    mockUseCoachSummary.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        generated_at: "2026-07-11T20:03:00Z",
        consents_pending: 0,
        insights_stale: 0,
        weekly_load: null,
      },
      error: null,
      refetch: vi.fn(),
    } as unknown as CoachSummaryQueryResult);

    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Todo al día — sin pendientes esta semana");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones en el estado degradado (coach-summary no disponible: WeeklyLoadMeter y 2 filas del inbox se omiten, el resto sigue visible)", async () => {
    vi.mocked(getAlerts).mockResolvedValue({
      overdue: 0,
      due_soon: 1,
      ok: 2,
      never_measured: 0,
      rapid_growth_count: 0,
      athletes: [
        buildAlert({
          athlete_id: 1,
          measurement_status: "due_soon",
          last_measurement_date: "2026-06-20",
          days_overdue: -3,
        }),
      ],
    });

    // Increment A sano: sesión + carrera + 3 filas no-agregadas del inbox.
    mockUseTrainingSessions.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [makeSession({ id: 42, scheduled_date: "2026-07-15" })],
      error: null,
      refetch: vi.fn(),
    } as unknown as TrainingSessionsQueryResult);

    mockUseRaceEventsList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          makeRaceEvent({ id: 501, event_date: "2026-06-10T12:00:00.000Z", has_results: false }),
          makeRaceEvent({ id: 77, event_date: "2026-08-01T12:00:00.000Z" }),
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
          { athlete_id: 1, newsletter_id: 1, status: "draft", generated_at: "2026-07-01T00:00:00Z", sent_at: null },
        ],
      },
      error: null,
      refetch: vi.fn(),
    } as unknown as NewsletterStatusQueryResult);

    // Increment B completamente no disponible (fallo genérico, NO cold
    // start): WeeklyLoadMeter y las filas "Consentimientos pendientes" /
    // "Insights IA desactualizados" deben omitirse en silencio (FR-004/005),
    // nunca con tono de error.
    mockUseCoachSummary.mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
      error: new Error("server error 500"),
      refetch: vi.fn(),
    } as unknown as CoachSummaryQueryResult);

    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Resultados por importar");
    expect(screen.queryByText("Carga semanal")).not.toBeInTheDocument();
    expect(screen.queryByText("Consentimientos pendientes")).not.toBeInTheDocument();
    expect(screen.queryByText("Insights IA desactualizados")).not.toBeInTheDocument();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it('no tiene violaciones en el estado cold-start/skeleton (todas las fuentes "despertando", nunca tono de error)', async () => {
    useServerWakingStore.setState({ isWaking: true });

    vi.mocked(getAlerts).mockReturnValue(new Promise(() => {})); // never resolves

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

    mockUseCoachSummary.mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
      error: null,
      refetch: vi.fn(),
    } as unknown as CoachSummaryQueryResult);

    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        {/* Hermano de la página, igual que AppShell — nunca dentro. */}
        <ServerWakingBanner />
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText(/La aplicación está iniciando/)).toBeInTheDocument();
    expect(screen.queryAllByRole("alert")).toHaveLength(0);

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("no tiene violaciones en la variante admin (todas las fuentes pobladas, fila 'Consentimientos pendientes' restringida)", async () => {
    authState.role = "admin";

    vi.mocked(getAlerts).mockResolvedValue({
      overdue: 10,
      due_soon: 0,
      ok: 0,
      never_measured: 0,
      rapid_growth_count: 0,
      // >8 (MAX_VISIBLE de MeasurementAlerts) para exponer también el link
      // "Ver todas (N)" en la variante admin.
      athletes: Array.from({ length: 10 }, (_, i) =>
        buildAlert({
          athlete_id: i + 1,
          athlete_name: `Atleta Ficticio ${i + 1}`,
          measurement_status: "overdue",
          last_measurement_date: "2026-04-01",
          days_overdue: 30 + i,
        }),
      ),
    });

    mockUseTrainingSessions.mockReturnValue({
      isLoading: false,
      isError: false,
      data: [makeSession({ id: 42, scheduled_date: "2026-07-15" })],
      error: null,
      refetch: vi.fn(),
    } as unknown as TrainingSessionsQueryResult);

    mockUseRaceEventsList.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          makeRaceEvent({ id: 501, event_date: "2026-06-10T12:00:00.000Z", has_results: false }),
          makeRaceEvent({ id: 77, event_date: "2026-08-01T12:00:00.000Z" }),
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
          { athlete_id: 1, newsletter_id: 1, status: "draft", generated_at: "2026-07-01T00:00:00Z", sent_at: null },
        ],
      },
      error: null,
      refetch: vi.fn(),
    } as unknown as NewsletterStatusQueryResult);

    mockUseCoachSummary.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        generated_at: "2026-07-11T20:03:00Z",
        consents_pending: 3,
        insights_stale: 1,
        weekly_load: [
          { age_band: "10-12", planned_minutes: 240, cap_minutes: 600, athlete_count: 8 },
        ],
      },
      error: null,
      refetch: vi.fn(),
    } as unknown as CoachSummaryQueryResult);

    const { container } = render(
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <MemoryRouter>
          <DashboardPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await screen.findByText("Atleta Ficticio 10");
    await screen.findByText("Consentimientos pendientes");
    // T050 — restringida para admin: renderizada como texto, no como link.
    expect(
      screen.getByText("Consentimientos pendientes").closest("a"),
    ).toBeNull();

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
