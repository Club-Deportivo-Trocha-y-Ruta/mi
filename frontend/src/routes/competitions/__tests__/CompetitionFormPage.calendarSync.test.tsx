/**
 * Tests T044 — Calendar Sync (Wave E, US5, FR-024).
 *
 * Verifica que `CompetitionFormPage` en modo create:
 *   1. Renderiza el checkbox "Crear evento en el calendario" marcado por default.
 *   2. Envía `create_calendar_event: true` en el body del POST race-event
 *      cuando el checkbox está activo (comportamiento por defecto).
 *   3. Envía `create_calendar_event: false` en el body del POST race-event
 *      cuando el coach desmarca el checkbox (opt-out).
 *
 * Nota: a diferencia de CompetitionFormPage.calendar.test.tsx (que testea
 * el flujo PR6 previo con POST /api/calendar/events por separado), estos tests
 * verifican que el flag viaja en el payload del propio POST race-event.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { axe } from "jest-axe";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "C", last_name: "T" },
      isAuthenticated: true,
    }),
  ),
}));

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>(
    "react-router-dom",
  );
  return { ...actual, useNavigate: () => mockNavigate };
});

import { mswServer } from "@/test/setup";
import {
  makeRaceEventRead,
  raceEventsHandlers,
} from "@/test/msw/raceEventsHandlers";
import { raceSeriesHandlers } from "@/test/msw/raceSeriesHandlers";
import { CompetitionFormPage } from "@/routes/competitions/CompetitionFormPage";

// ── Helpers ──────────────────────────────────────────────────────────────────

function renderCreate() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/competitions/new"]}>
        <Routes>
          <Route
            path="/competitions/new"
            element={<CompetitionFormPage mode="create" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Rellena los campos obligatorios y hace clic en "Crear competencia".
 * Retorna el valor del campo `create_calendar_event` del body interceptado.
 */
async function fillSubmitAndCaptureBody(): Promise<Record<string, unknown> | null> {
  let capturedBody: Record<string, unknown> | null = null;

  mswServer.use(
    http.post("*/api/race-analysis/race-events/", async ({ request }) => {
      capturedBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(makeRaceEventRead({ id: 42 }), { status: 201 });
    }),
  );

  const user = userEvent.setup();

  // Spec 014: el picker de serie es requerido. Esperamos que cargue y
  // seleccionamos la copa (id=2 según raceSeriesHandlers).
  const seriesSelect = await screen.findByLabelText(/Serie/i);
  await waitFor(() =>
    expect(
      Array.from((seriesSelect as HTMLSelectElement).options).some(
        (o) => o.value === "2",
      ),
    ).toBe(true),
  );
  await user.selectOptions(seriesSelect, "2");

  await user.selectOptions(screen.getByLabelText("Número de válida"), "4");
  await user.type(screen.getByLabelText("Nombre"), "Válida 4 · Cali");
  // Seleccionar sede en modo predefined (el select tiene label con texto "Sede")
  const sedeSelect = screen.getByRole("combobox", {
    name: /Sede/,
  });
  await user.selectOptions(sedeSelect, "Cali");
  await user.type(screen.getByLabelText("Fecha"), "2026-05-17");
  await user.click(screen.getByRole("button", { name: /Crear competencia/i }));

  await waitFor(() => expect(capturedBody).not.toBeNull());
  return capturedBody;
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  // Spec 014: el picker de serie es requerido. Registramos los handlers de
  // race-series para que el select cargue la lista (copa por defecto, id=2).
  mswServer.use(...raceEventsHandlers, ...raceSeriesHandlers);
});

// ── Suite ─────────────────────────────────────────────────────────────────────

describe("CompetitionFormPage — FR-024 calendar sync payload", () => {
  it("checkbox 'Crear evento en el calendario' está visible y marcado por default", () => {
    renderCreate();
    const cb = screen.getByTestId(
      "create-calendar-event-checkbox",
    ) as HTMLInputElement;
    expect(cb).toBeInTheDocument();
    expect(cb.checked).toBe(true);
  });

  it("checkbox está en una sección 'Calendario' y es opt-out visible", () => {
    renderCreate();
    // La sección existe solo en create
    expect(
      screen.getByRole("heading", { name: "Calendario", level: 2 }),
    ).toBeInTheDocument();
    // Label descriptivo presente
    expect(
      screen.getByText(/Crear evento en el calendario del club/i),
    ).toBeInTheDocument();
  });

  it("checkbox NO aparece en modo edit", async () => {
    mswServer.use(
      http.get("*/api/race-analysis/race-events/:id", () =>
        HttpResponse.json(makeRaceEventRead({ id: 1 })),
      ),
    );
    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 } },
    });
    render(
      <QueryClientProvider client={qc}>
        <MemoryRouter initialEntries={["/competitions/1/edit"]}>
          <Routes>
            <Route
              path="/competitions/:id/edit"
              element={<CompetitionFormPage mode="edit" />}
            />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    // Esperar que cargue el formulario
    await screen.findByLabelText("Nombre");
    expect(
      screen.queryByTestId("create-calendar-event-checkbox"),
    ).not.toBeInTheDocument();
  });

  it("con checkbox ON (default) envía create_calendar_event=true en el POST", async () => {
    renderCreate();
    const body = await fillSubmitAndCaptureBody();
    expect(body).toMatchObject({ create_calendar_event: true });
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/42"),
    );
  });

  it("con checkbox OFF envía create_calendar_event=false en el POST", async () => {
    renderCreate();
    // Desmarcar el checkbox antes de rellenar el formulario
    const user = userEvent.setup();
    const cb = screen.getByTestId("create-calendar-event-checkbox");
    await user.click(cb);

    const body = await fillSubmitAndCaptureBody();
    expect(body).toMatchObject({ create_calendar_event: false });
  });

  it("0 violaciones axe en el formulario vacío de create", async () => {
    const { container } = renderCreate();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
