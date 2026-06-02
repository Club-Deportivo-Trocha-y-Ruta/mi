/**
 * Tests PR6 (calendario bidireccional) — checkbox "Crear evento en calendario".
 *
 * Cubre:
 *  - Checkbox visible y ON por default en modo create.
 *  - Checkbox NO visible en modo edit.
 *  - Submit con checkbox ON → POST race-event + POST calendar con race_event_id.
 *  - Submit con checkbox OFF → solo POST race-event (sin POST calendar).
 *  - Fallo del POST calendar no bloquea la navegación (best-effort).
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

async function fillAndSubmit() {
  const user = userEvent.setup();
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

describe("CompetitionFormPage — PR6 checkbox calendario", () => {
  it("checkbox visible y ON por default en create", () => {
    renderCreate();
    const cb = screen.getByTestId(
      "create-calendar-event-checkbox",
    ) as HTMLInputElement;
    expect(cb).toBeInTheDocument();
    expect(cb.checked).toBe(true);
  });

  it("checkbox ON → crea calendar_event con race_event_id del id creado", async () => {
    let calendarBody: Record<string, unknown> | null = null;
    mswServer.use(
      http.post("*/api/calendar/events", async ({ request }) => {
        calendarBody = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({ id: 900 }, { status: 201 });
      }),
    );

    renderCreate();
    await fillAndSubmit();

    await waitFor(() => expect(calendarBody).not.toBeNull());
    expect(calendarBody).toMatchObject({
      event_type: "competition",
      race_event_id: 555,
      title: "Válida 4 · Cali",
      all_day: true,
    });
    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/555"),
    );
  });

  it("checkbox OFF → NO crea calendar_event", async () => {
    let calendarCalled = false;
    mswServer.use(
      http.post("*/api/calendar/events", () => {
        calendarCalled = true;
        return HttpResponse.json({ id: 900 }, { status: 201 });
      }),
    );

    const user = userEvent.setup();
    renderCreate();
    await user.click(screen.getByTestId("create-calendar-event-checkbox"));
    await fillAndSubmit();

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/555"),
    );
    expect(calendarCalled).toBe(false);
  });

  it("fallo del POST calendar no bloquea la navegación", async () => {
    mswServer.use(
      http.post(
        "*/api/calendar/events",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );

    renderCreate();
    await fillAndSubmit();

    await waitFor(() =>
      expect(mockNavigate).toHaveBeenCalledWith("/competitions/555"),
    );
  });
});
