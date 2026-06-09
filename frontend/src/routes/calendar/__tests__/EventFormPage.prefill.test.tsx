/**
 * Tests para el pre-relleno del formulario de calendario desde una válida (US2).
 *
 * Feature: 008-associate-competition-calendar — User Story 2 (edit details first)
 *
 * Cubre:
 *  - Con ?race_event_id=N, el formulario muestra el título/fecha/ubicación de la válida.
 *  - El tipo de evento es "Competencia" (competition).
 *  - El campo "Todo el día" está activado.
 *  - Al enviar, la mutación createCalendarEvent se llama con los datos pre-rellenados.
 *  - 0 violaciones jest-axe en la página pre-rellenada.
 *
 * Lo que NO se prueba aquí:
 *  - Modo edición de CalendarEvent (cubierto en CalendarPage.test.tsx).
 *  - Split button de CompetitionDetailPage (cubierto en CompetitionDetailPage.associate.test.tsx).
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

import { useAuthStore } from "@/store/auth.store";
import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventsHandlers,
} from "@/test/msw/raceEventsHandlers";
import { calendarHandlers } from "@/test/msw/calendarHandlers";
import { EventFormPage } from "@/routes/calendar/EventFormPage";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function mockAuthAs(role: "coach" | "admin" = "coach") {
  const state = {
    accessToken: "test-token",
    user: { id: 1, role, first_name: "E", last_name: "T" },
    isAuthenticated: true,
  };
  vi.mocked(useAuthStore).mockImplementation(
    ((sel: (s: typeof state) => unknown) => sel(state)) as unknown as typeof useAuthStore,
  );
}

/**
 * Renders EventFormPage (create mode) with an optional race_event_id query param.
 */
function renderCreateForm(raceEventId?: number) {
  const path = raceEventId != null
    ? `/calendar/events/new?race_event_id=${raceEventId}`
    : "/calendar/events/new";

  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });

  const ui = render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route
            path="/calendar/events/new"
            element={<EventFormPage mode="create" />}
          />
          <Route path="/calendar" element={<div data-testid="calendar-page">calendario</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { ...ui, qc };
}

// ---------------------------------------------------------------------------
// Fixture
// ---------------------------------------------------------------------------

const VALIDA = makeRaceEventRead({
  id: 5,
  name: "Copa Valle — Válida V Palmira",
  event_date: "2026-08-01",
  location: "Palmira",
  status: "scheduled",
  has_calendar_event: false,
});

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...raceEventsHandlers);
  mswServer.use(...calendarHandlers);
  // Override GET /race-events/5 to return our fixture
  mswServer.use(
    http.get("*/api/race-analysis/race-events/5", () =>
      HttpResponse.json(VALIDA),
    ),
  );
  // Override available-for-calendar to return the valida
  mswServer.use(
    http.get("*/api/race-analysis/race-events/available-for-calendar", () =>
      HttpResponse.json([
        {
          id: 5,
          name: "Copa Valle — Válida V Palmira",
          event_date: "2026-08-01",
          sequence_number: 5,
          location: "Palmira",
          series_id: 1,
        },
      ]),
    ),
  );
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("EventFormPage — prefill desde válida (US2)", () => {
  it("muestra skeleton mientras carga la válida", async () => {
    // Controlamos el timing de la respuesta para capturar el skeleton
    let resolveRaceEvent!: () => void;
    const pendingRaceEvent = new Promise<void>(
      (resolve) => (resolveRaceEvent = resolve),
    );

    mswServer.use(
      http.get("*/api/race-analysis/race-events/5", async () => {
        await pendingRaceEvent;
        return HttpResponse.json(VALIDA);
      }),
    );

    mockAuthAs("coach");
    renderCreateForm(5);

    // El skeleton debe estar presente durante la carga
    const skeletons = document.querySelectorAll(".animate-pulse");
    expect(skeletons.length).toBeGreaterThan(0);

    resolveRaceEvent();
  });

  it("pre-rellena el título con el nombre de la válida", async () => {
    mockAuthAs("coach");
    renderCreateForm(5);

    const titleInput = await screen.findByLabelText<HTMLInputElement>("Título");
    await waitFor(() =>
      expect(titleInput.value).toBe("Copa Valle — Válida V Palmira"),
    );
  });

  it("pre-rellena la fecha con event_date de la válida", async () => {
    mockAuthAs("coach");
    renderCreateForm(5);

    const dateInput = await screen.findByLabelText<HTMLInputElement>("Fecha");
    await waitFor(() => expect(dateInput.value).toBe("2026-08-01"));
  });

  it("pre-rellena la ubicación con el location de la válida", async () => {
    mockAuthAs("coach");
    renderCreateForm(5);

    const locationInput = await screen.findByLabelText<HTMLInputElement>(
      /lugar/i,
    );
    await waitFor(() => expect(locationInput.value).toBe("Palmira"));
  });

  it("activa 'Todo el día' cuando viene race_event_id", async () => {
    mockAuthAs("coach");
    renderCreateForm(5);

    const allDayCheckbox = await screen.findByRole<HTMLInputElement>(
      "checkbox",
      { name: /todo el día/i },
    );
    await waitFor(() => expect(allDayCheckbox.checked).toBe(true));
  });

  it("selecciona event_type=competition cuando viene race_event_id", async () => {
    mockAuthAs("coach");
    renderCreateForm(5);

    // La radio de "Competencia" debe estar checked
    const competenciaRadio = await screen.findByRole<HTMLInputElement>("radio", {
      name: /competencia/i,
    });
    await waitFor(() => expect(competenciaRadio.checked).toBe(true));
  });

  it("al enviar el formulario (competition con datos completos) llama POST /calendar/events", async () => {
    let postBody: unknown = null;
    mswServer.use(
      http.post("*/api/calendar/events", async ({ request }) => {
        postBody = await request.json();
        return HttpResponse.json(
          {
            id: 200,
            club_id: 1,
            event_type: "competition",
            status: "scheduled",
            title: "Copa Valle — Válida V Palmira",
            description: "",
            location: "Palmira",
            start_at: "2026-08-01T00:00:00",
            end_at: "2026-08-01T23:59:59",
            all_day: true,
            timezone: "America/Bogota",
            event_data: {},
            color_hex: null,
            race_event_id: 5,
            created_by_user_id: 1,
            created_at: "2026-06-09T00:00:00Z",
            updated_at: "2026-06-09T00:00:00Z",
            audiences: [{ audience_type: "all_club", audience_value: {} }],
          },
          { status: 201 },
        );
      }),
    );

    mockAuthAs("coach");
    const user = userEvent.setup();
    renderCreateForm(5);

    // Esperamos a que el título esté pre-rellenado (indica que la carga terminó)
    const titleInput = await screen.findByLabelText<HTMLInputElement>("Título");
    await waitFor(() =>
      expect(titleInput.value).toBe("Copa Valle — Válida V Palmira"),
    );

    // Para que el formulario sea válido en competition type, necesitamos rellenar
    // "Ciudad" (data_competition.city es obligatorio por el schema Zod).
    // Navegamos a la tab "Datos específicos".
    await user.click(screen.getByRole("tab", { name: /datos específicos/i }));
    const cityInput = await screen.findByLabelText<HTMLInputElement>("Ciudad");
    await user.type(cityInput, "Palmira");

    // Enviamos el formulario
    const submitBtn = screen.getByRole("button", { name: /crear evento/i });
    await user.click(submitBtn);

    // Verificamos que se llamó el endpoint
    await waitFor(() => expect(postBody).not.toBeNull());
    const body = postBody as Record<string, unknown>;
    expect(body.event_type).toBe("competition");
    expect(body.title).toBe("Copa Valle — Válida V Palmira");
    expect(body.all_day).toBe(true);
  });

  it("sin race_event_id, el formulario arranca vacío y no activa todo-el-día", async () => {
    mockAuthAs("coach");
    renderCreateForm(); // sin race_event_id

    // Esperamos a que el formulario renderice
    await screen.findByRole("button", { name: /crear evento/i });

    const titleInput = screen.getByLabelText<HTMLInputElement>("Título");
    expect(titleInput.value).toBe("");

    const allDayCheckbox = screen.getByRole<HTMLInputElement>("checkbox", {
      name: /todo el día/i,
    });
    expect(allDayCheckbox.checked).toBe(false);
  });

  it("0 violaciones jest-axe con el formulario pre-rellenado", async () => {
    mockAuthAs("coach");
    const { container } = renderCreateForm(5);

    // Esperamos a que se resuelva el pre-relleno
    await screen.findByLabelText<HTMLInputElement>("Título");
    await waitFor(() => {
      const input = container.querySelector<HTMLInputElement>("#event-title");
      return input && input.value === "Copa Valle — Válida V Palmira";
    });

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
