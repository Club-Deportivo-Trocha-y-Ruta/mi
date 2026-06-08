/**
 * Tests FR-024 (calendario bidireccional) — checkbox "Crear evento en calendario".
 *
 * Cubre:
 *  - Checkbox visible y ON por default en modo create.
 *  - Checkbox NO visible en modo edit.
 *  - Submit con checkbox ON → POST race-event incluye create_calendar_event=true.
 *  - Submit con checkbox OFF → POST race-event incluye create_calendar_event=false.
 *  - El backend gestiona la creación del calendar_event de forma transaccional;
 *    el frontend no hace POST a /api/calendar/events por separado.
 *
 * Nota de migración (PR6 → FR-024):
 *   La versión anterior (PR6) creaba el calendar_event mediante un POST separado
 *   al endpoint /api/calendar/events. Desde Wave E, el flag `create_calendar_event`
 *   va en el body del POST race-event y el backend lo resuelve transaccionalmente.
 *   Estos tests reflejan el comportamiento actual.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { http, HttpResponse } from "msw";

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
import { CompetitionFormPage } from "@/routes/competitions/CompetitionFormPage";

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

async function fillAndSubmit(user = userEvent.setup()) {
  await user.selectOptions(screen.getByLabelText("Número de válida"), "4");
  await user.type(screen.getByLabelText("Nombre"), "Válida 4 · Cali");
  await user.selectOptions(screen.getByLabelText(/Sede/), "Cali");
  await user.type(screen.getByLabelText("Fecha"), "2026-05-17");
  await user.click(screen.getByRole("button", { name: /Crear competencia/i }));
  return user;
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...raceEventsHandlers);
  mswServer.use(
    http.post("*/api/race-analysis/race-events/", () =>
      HttpResponse.json(makeRaceEventRead({ id: 555 }), { status: 201 }),
    ),
  );
});

describe("CompetitionFormPage — FR-024 checkbox calendario", () => {
  it("checkbox visible y ON por default en create", () => {
    renderCreate();
    const cb = screen.getByTestId(
      "create-calendar-event-checkbox",
    ) as HTMLInputElement;
    expect(cb).toBeInTheDocument();
    expect(cb.checked).toBe(true);
  });

  it("checkbox ON → POST race-event incluye create_calendar_event=true en el payload", async () => {
    let raceEventBody: Record<string, unknown> | null = null;
    let calendarCalled = false;

    mswServer.use(
      http.post("*/api/race-analysis/race-events/", async ({ request }) => {
        raceEventBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeRaceEventRead({ id: 555 }), { status: 201 });
      }),
      // El POST al endpoint de calendarios NO debe llamarse — el backend lo gestiona
      http.post("*/api/calendar/events", () => {
        calendarCalled = true;
        return HttpResponse.json({ id: 900 }, { status: 201 });
      }),
    );

    renderCreate();
    await fillAndSubmit();

    await waitFor(() => expect(raceEventBody).not.toBeNull());
    expect(raceEventBody).toMatchObject({ create_calendar_event: true });
    // El frontend no llama a /api/calendar/events por separado
    expect(calendarCalled).toBe(false);
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/555"),
    );
  });

  it("checkbox OFF → POST race-event incluye create_calendar_event=false", async () => {
    let raceEventBody: Record<string, unknown> | null = null;

    mswServer.use(
      http.post("*/api/race-analysis/race-events/", async ({ request }) => {
        raceEventBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json(makeRaceEventRead({ id: 555 }), { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderCreate();
    // Desmarcar el checkbox antes de rellenar
    await user.click(screen.getByTestId("create-calendar-event-checkbox"));
    await fillAndSubmit(user);

    await waitFor(() => expect(raceEventBody).not.toBeNull());
    expect(raceEventBody).toMatchObject({ create_calendar_event: false });
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/555"),
    );
  });

  it("navega al detalle tras crear con éxito (checkbox ON por default)", async () => {
    renderCreate();
    await fillAndSubmit();

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/555"),
    );
  });
});
