/**
 * Tests T044 — Calendar Sync (Wave E, US5, FR-024).
 *
 * Verifica que el checkbox "Crear evento en el calendario" de
 * `CompetitionFormPage` en modo create vive en su propia sección visible y
 * desaparece en modo edit; incluye el barrido jest-axe del formulario vacío.
 *
 * La cobertura de "checkbox marcado por default" y "el flag viaja en el
 * payload del POST race-event" vive en CompetitionFormPage.calendar.test.tsx
 * (esos tests además verifican que no se hace un POST separado a
 * /api/calendar/events) — no se duplica aquí.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
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

// ── Fixtures ─────────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  // Spec 014: el picker de serie es requerido. Registramos los handlers de
  // race-series para que el select cargue la lista (copa por defecto, id=2).
  mswServer.use(...raceEventsHandlers, ...raceSeriesHandlers);
});

// ── Suite ─────────────────────────────────────────────────────────────────────

describe("CompetitionFormPage — FR-024 calendar sync payload", () => {
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

  it("0 violaciones axe en el formulario vacío de create", async () => {
    const { container } = renderCreate();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
