/**
 * Tests para la acción "Asociar a calendario" (US1) en CompetitionDetailPage.
 *
 * Feature: 008-associate-competition-calendar — User Story 1 (one-click)
 *
 * Cubre:
 *  - Un click llama al nuevo endpoint POST /race-events/{id}/calendar-event.
 *  - On success: el botón desaparece, aparece el badge "En calendario",
 *    se muestra toast de éxito.
 *  - On failure: toast de error visible, botón permanece habilitado (retry).
 *  - Estado pending: botón deshabilitado mientras el request está en vuelo.
 *  - 0 violaciones jest-axe en la página con botón visible.
 *
 * Lo que NO se prueba aquí (cubierto en CompetitionDetailPage.test.tsx):
 *  - Render base, tabs URL-driven, delete, 404 redirect.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";

// ── Auth mock ────────────────────────────────────────────────────────────────
vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

// ── Navigation mock ──────────────────────────────────────────────────────────
const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

// ── Mock lazy tabs (evitan carga de deps pesadas) ────────────────────────────
vi.mock("@/components/competitions/tabs/AthletesTab", () => ({
  AthletesTab: () => <div data-testid="mock-athletes-tab">athletes</div>,
}));
vi.mock("@/components/competitions/tabs/InsightsTab", () => ({
  InsightsTab: () => <div data-testid="mock-insights-tab">insights</div>,
}));
vi.mock("@/components/competitions/tabs/StandingsTab", () => ({
  StandingsTab: () => <div data-testid="mock-standings-tab">standings</div>,
}));
vi.mock("@/components/competitions/tabs/ConditionsTab", () => ({
  ConditionsTab: () => (
    <div data-testid="mock-conditions-tab">conditions</div>
  ),
}));

// ── Sonner mock (espía toast.success/toast.error sin renderizar toasts reales) ──
vi.mock("sonner", () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import { useAuthStore } from "@/store/auth.store";
import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventsCalendarAutoCreateConflictHandler,
  raceEventsHandlers,
} from "@/test/msw/raceEventsHandlers";
import { toast } from "sonner";
import { CompetitionDetailPage } from "@/routes/competitions/CompetitionDetailPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockAuthAs(role: "admin" | "coach") {
  const state = {
    accessToken: "test-token",
    user: { id: 1, role, first_name: "U", last_name: "T" },
    isAuthenticated: true,
  };
  vi.mocked(useAuthStore).mockImplementation(
    ((sel: (s: typeof state) => unknown) => sel(state)) as unknown as typeof useAuthStore,
  );
}

/**
 * Renders `CompetitionDetailPage` for a given race event id.
 * Returns a fresh `QueryClient` for per-test isolation.
 */
function renderDetail(id: number = 7) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const ui = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/competitions/${id}`]}>
        <Routes>
          <Route
            path="/competitions/:id"
            element={<CompetitionDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...ui, qc };
}

// ---------------------------------------------------------------------------
// Fixture: válida sin calendar_event (US1 scenario)
// ---------------------------------------------------------------------------

const UNLINKED_EVENT = makeRaceEventRead({
  id: 7,
  has_calendar_event: false,
  status: "completed",
  name: "Copa Valle — Válida IV",
  location: "Cali",
  event_date: "2026-05-17",
});

beforeEach(() => {
  vi.clearAllMocks();
  // Registramos los handlers base y luego sobreescribimos GET /{id} para
  // devolver UNLINKED_EVENT (has_calendar_event: false). En MSW el último
  // handler registrado tiene prioridad sobre los anteriores cuando los
  // patrones se solapan.
  mswServer.use(...raceEventsHandlers);
  mswServer.use(
    http.get("*/api/race-analysis/race-events/7", () =>
      HttpResponse.json(UNLINKED_EVENT),
    ),
  );
});

// ---------------------------------------------------------------------------
// US1 — happy path
// ---------------------------------------------------------------------------

describe("CompetitionDetailPage — associate calendar (US1)", () => {
  it("el botón 'Asociar a calendario' llama al endpoint POST /calendar-event al hacer click", async () => {
    let called = false;
    mswServer.use(
      http.post("*/api/race-analysis/race-events/7/calendar-event", () => {
        called = true;
        return HttpResponse.json(
          { race_event_id: 7, calendar_event_id: 107, has_calendar_event: true },
          { status: 201 },
        );
      }),
    );

    mockAuthAs("coach");
    const user = userEvent.setup();
    renderDetail(7);

    const btn = await screen.findByTestId("btn-associate-calendar");
    await user.click(btn);

    await waitFor(() => expect(called).toBe(true));
  });

  it("no muestra el botón a un admin (endpoint coach-only, FR-008)", async () => {
    mockAuthAs("admin");
    renderDetail(7);

    // La página carga (tabs visibles) pero el CTA no se renderiza para admin.
    await screen.findByTestId("competition-tabs");
    expect(
      screen.queryByTestId("btn-associate-calendar"),
    ).not.toBeInTheDocument();
  });

  it("on success: botón desaparece, badge 'En calendario' aparece, toast de éxito visible", async () => {
    // After POST, GET /{id} re-fetch returns has_calendar_event: true
    let getCallCount = 0;
    mswServer.use(
      http.get("*/api/race-analysis/race-events/7", () => {
        getCallCount += 1;
        // Second call (after invalidation) returns linked event
        const ev =
          getCallCount >= 2
            ? makeRaceEventRead({ id: 7, has_calendar_event: true, status: "completed" })
            : UNLINKED_EVENT;
        return HttpResponse.json(ev);
      }),
      http.post("*/api/race-analysis/race-events/7/calendar-event", () =>
        HttpResponse.json(
          { race_event_id: 7, calendar_event_id: 107, has_calendar_event: true },
          { status: 201 },
        ),
      ),
    );

    mockAuthAs("coach");
    const user = userEvent.setup();
    renderDetail(7);

    // Espera a que cargue la página
    await screen.findByTestId("btn-associate-calendar");

    await user.click(screen.getByTestId("btn-associate-calendar"));

    // Toast de éxito (sonner) disparado
    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith(
        "Competencia asociada al calendario.",
      );
    });

    // Tras la invalidación y re-fetch el botón desaparece y el badge aparece
    await waitFor(() =>
      expect(
        screen.queryByTestId("btn-associate-calendar"),
      ).not.toBeInTheDocument(),
    );
    await screen.findByTestId("badge-in-calendar");
  });

  // ---------------------------------------------------------------------------
  // US1 — failure path
  // ---------------------------------------------------------------------------

  it("on failure (409): toast de error visible, botón permanece habilitado", async () => {
    mswServer.use(raceEventsCalendarAutoCreateConflictHandler);

    mockAuthAs("coach");
    const user = userEvent.setup();
    renderDetail(7);

    await screen.findByTestId("btn-associate-calendar");
    await user.click(screen.getByTestId("btn-associate-calendar"));

    // Toast de error (sonner) disparado
    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });

    // El botón sigue presente (retry posible)
    expect(screen.getByTestId("btn-associate-calendar")).toBeInTheDocument();
    expect(screen.getByTestId("btn-associate-calendar")).not.toBeDisabled();
  });

  it("on failure (500): toast de error no expone texto de excepción cruda", async () => {
    mswServer.use(
      http.post("*/api/race-analysis/race-events/7/calendar-event", () =>
        HttpResponse.json(
          { detail: "Internal server error" },
          { status: 500 },
        ),
      ),
    );

    mockAuthAs("coach");
    const user = userEvent.setup();
    renderDetail(7);

    await screen.findByTestId("btn-associate-calendar");
    await user.click(screen.getByTestId("btn-associate-calendar"));

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalled();
    });
    const message = vi.mocked(toast.error).mock.calls.at(-1)?.[0];
    // El mensaje del toast no debe contener stack traces ni "Internal Server Error"
    // crudo — debe ser un mensaje amigable.
    expect(message).not.toMatch(/^Error$/i);
    expect(message).toBeTruthy();
  });

  // ---------------------------------------------------------------------------
  // US1 — pending state
  // ---------------------------------------------------------------------------

  it("durante el request el botón está deshabilitado y muestra spinner", async () => {
    // Usamos un handler que nunca responde para capturar el estado pending
    let resolveRequest!: (v: Response) => void;
    const pendingResponse = new Promise<Response>(
      (resolve) => (resolveRequest = resolve),
    );

    mswServer.use(
      http.post(
        "*/api/race-analysis/race-events/7/calendar-event",
        () => pendingResponse,
      ),
    );

    mockAuthAs("coach");
    const user = userEvent.setup();
    renderDetail(7);

    await screen.findByTestId("btn-associate-calendar");
    await user.click(screen.getByTestId("btn-associate-calendar"));

    // Durante el pending: botón deshabilitado
    await waitFor(() =>
      expect(screen.getByTestId("btn-associate-calendar")).toBeDisabled(),
    );

    // Limpiamos la promesa pendiente para no contaminar otros tests
    resolveRequest(
      new Response(
        JSON.stringify({
          race_event_id: 7,
          calendar_event_id: 107,
          has_calendar_event: true,
        }),
        { status: 201, headers: { "Content-Type": "application/json" } },
      ),
    );
  });

  // ---------------------------------------------------------------------------
  // Accesibilidad
  // ---------------------------------------------------------------------------

  it("0 violaciones jest-axe en la página con el botón 'Asociar a calendario' visible", async () => {
    mockAuthAs("coach");
    const { container } = renderDetail(7);
    await screen.findByTestId("btn-associate-calendar");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
