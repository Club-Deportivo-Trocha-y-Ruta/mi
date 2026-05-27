/**
 * Tests vitest para el prefill CF6 de EventForm (race_event_id desde
 * CompetitionDetailPage).
 *
 * Cubre:
 *  - prefillRaceEventId=100 → event_type arranca "competition" + race_event_id=100.
 *  - Dropdown vacio + event_type=competition → link "Crear nueva válida"
 *    visible con href correcto.
 *  - EventFormPage con ?race_event_id=42 → pasa prefill a EventForm.
 *
 * Estos tests COMPLEMENTAN EventForm.race-event-id.test.tsx (FE-2) —
 * no duplican.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Routes, Route } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "Coach", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/api/calendar", async () => {
  const actual = await vi.importActual<typeof import("@/api/calendar")>(
    "@/api/calendar",
  );
  return {
    ...actual,
    useCreateCalendarEvent: vi.fn(),
    useUpdateCalendarEvent: vi.fn(),
    useCalendarEvent: vi.fn(() => ({
      data: undefined,
      isLoading: false,
      isError: false,
    })),
  };
});

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: () => ({
    data: { items: [] },
    isLoading: false,
  }),
}));

import {
  useCreateCalendarEvent,
  useUpdateCalendarEvent,
} from "@/api/calendar";
import { mswServer } from "@/test/setup";
import { EventForm } from "@/components/calendar/EventForm";
import { EventFormPage } from "@/routes/calendar/EventFormPage";

const mutateAsync = vi.fn();
const mutationStub = {
  mutateAsync,
  mutate: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  isIdle: true,
  reset: vi.fn(),
  data: undefined,
  error: null,
  variables: undefined,
  context: undefined,
  status: "idle" as const,
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
};

function renderForm(prefillRaceEventId?: number) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <EventForm
          mode="create"
          onSuccess={vi.fn()}
          onCancel={vi.fn()}
          prefillRaceEventId={prefillRaceEventId}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderEventFormPage(initialEntry: string) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialEntry]}>
        <Routes>
          <Route
            path="/calendar/events/new"
            element={<EventFormPage mode="create" />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mutateAsync.mockClear();
  vi.mocked(useCreateCalendarEvent).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useCreateCalendarEvent>,
  );
  vi.mocked(useUpdateCalendarEvent).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useUpdateCalendarEvent>,
  );
});

describe("EventForm — prefill CF6", () => {
  it("prefillRaceEventId=100 → event_type arranca 'competition' y race_event_id=100", async () => {
    const user = userEvent.setup();
    renderForm(100);

    // El radio de "Competencia" debe estar seleccionado por default.
    // El input radio existe pero esta sr-only; verificamos el state via
    // el seguimiento del valor del campo race_event_id.
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      const select = screen.getByTestId(
        "event-race-event-id",
      ) as HTMLSelectElement;
      expect(select.value).toBe("100");
    });
  });

  it("dropdown vacio + event_type=competition → link 'Crear nueva válida' con href correcto", async () => {
    // Forzamos response vacio del endpoint available-for-calendar
    mswServer.use(
      http.get("*/api/race-events/available-for-calendar", () =>
        HttpResponse.json([]),
      ),
    );
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Competencia"));
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() =>
      expect(
        screen.getByTestId("event-race-event-create-link"),
      ).toBeInTheDocument(),
    );
    const link = screen.getByTestId("event-race-event-create-link");
    expect(link).toHaveAttribute(
      "href",
      "/competitions/new?returnTo=/calendar/events/new",
    );
  });
});

describe("EventFormPage — query param race_event_id", () => {
  it("?race_event_id=42 pasa el prefill a EventForm", async () => {
    // El id 42 debe existir en el dropdown de available-for-calendar para
    // que <option value="42"> exista y select.value pueda asumir "42".
    mswServer.use(
      http.get("*/api/race-events/available-for-calendar", () =>
        HttpResponse.json([
          {
            id: 42,
            name: "Válida para prefill",
            event_date: "2026-05-17",
            sequence_number: 4,
            location: "Cali",
            series_id: 1,
          },
        ]),
      ),
    );
    const user = userEvent.setup();
    renderEventFormPage("/calendar/events/new?race_event_id=42");
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      const select = screen.getByTestId(
        "event-race-event-id",
      ) as HTMLSelectElement;
      expect(select.value).toBe("42");
    });
  });
});
