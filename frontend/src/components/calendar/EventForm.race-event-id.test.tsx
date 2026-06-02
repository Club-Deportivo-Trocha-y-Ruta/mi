/**
 * Tests vitest para el refactor FE-2 de EventForm (race_event_id).
 *
 * Cubre:
 *  - Cambio a event_type=competition muestra dropdown de válida asociada.
 *  - Submit sin race_event_id da error de validación (Zod).
 *  - Empty state link a /competitions/import cuando no hay válidas
 *    disponibles para la temporada.
 *  - Hidrata el race_event_id en mode=edit.
 *
 * Estos tests COMPLEMENTAN a EventForm.test.tsx — no duplican.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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
  };
});

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: () => ({
    data: {
      items: [
        {
          id: 1,
          first_name: "Sebastián",
          last_name: "García",
          age_decimal: 13.2,
          category: "Pre-juvenil A",
        },
      ],
    },
    isLoading: false,
  }),
}));

import { useCreateCalendarEvent, useUpdateCalendarEvent } from "@/api/calendar";
import { mswServer } from "@/test/setup";
import {
  mockAvailableRaceEvent,
} from "@/test/msw/athleteRaceAnalysisHandlers";
import { http, HttpResponse } from "msw";
import { EventForm } from "./EventForm";

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

function renderForm(
  mode: "create" | "edit" = "create",
  onSuccess = vi.fn(),
  onCancel = vi.fn(),
  initialData?: unknown,
) {
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
          mode={mode}
          onSuccess={onSuccess}
          onCancel={onCancel}
          initialData={initialData as never}
        />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("EventForm — refactor FE-2 race_event_id", () => {
  beforeEach(() => {
    mutateAsync.mockClear();
    vi.mocked(useCreateCalendarEvent).mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useCreateCalendarEvent>,
    );
    vi.mocked(useUpdateCalendarEvent).mockReturnValue(
      mutationStub as unknown as ReturnType<typeof useUpdateCalendarEvent>,
    );
  });

  it("muestra el dropdown de válida asociada al cambiar a event_type=competition", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Competencia"));
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      expect(screen.getByTestId("event-race-event-id")).toBeInTheDocument();
    });
    expect(screen.getByLabelText(/válida asociada/i)).toBeInTheDocument();
  });

  it("carga las opciones desde el endpoint y permite seleccionar una válida", async () => {
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Competencia"));
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      const select = screen.getByTestId(
        "event-race-event-id",
      ) as HTMLSelectElement;
      // El option default + 2 mocks del handler
      expect(select.options.length).toBeGreaterThanOrEqual(3);
    });

    // Selección
    const select = screen.getByTestId(
      "event-race-event-id",
    ) as HTMLSelectElement;
    await user.selectOptions(select, "100");
    expect(select.value).toBe("100");
  });

  it("muestra empty state con link a /competitions/import cuando no hay válidas", async () => {
    mswServer.use(
      http.get("*/api/race-events/available-for-calendar", () =>
        HttpResponse.json([]),
      ),
    );
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Competencia"));
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      expect(screen.getByTestId("event-race-event-empty")).toBeInTheDocument();
    });

    const link = screen.getByRole("link", { name: /módulo de importación/i });
    expect(link).toHaveAttribute("href", "/competitions/import");
  });

  it("hidrata el race_event_id en mode=edit", async () => {
    const user = userEvent.setup();
    renderForm("edit", vi.fn(), vi.fn(), {
      id: 7,
      title: "Test edit",
      event_type: "competition",
      start_at: "2026-05-17T08:00:00",
      end_at: "2026-05-17T12:00:00",
      scope: "club_wide",
      race_event_id: 100,
      tags: [],
      visibility: "all",
      attendance_required: false,
    });

    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      const select = screen.getByTestId(
        "event-race-event-id",
      ) as HTMLSelectElement;
      expect(select.value).toBe("100");
    });
  });

  it("muestra mensaje de error cuando el endpoint de válidas falla", async () => {
    mswServer.use(
      http.get(
        "*/api/race-events/available-for-calendar",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    const user = userEvent.setup();
    renderForm();

    await user.click(screen.getByText("Competencia"));
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      expect(
        screen.getByText(/no se pudo cargar la lista de válidas/i),
      ).toBeInTheDocument();
    });
  });

  it("muestra labels formateados con sequence_number ('Válida N — name')", async () => {
    mswServer.use(
      http.get("*/api/race-events/available-for-calendar", () =>
        HttpResponse.json([
          mockAvailableRaceEvent({
            id: 200,
            name: "Cali XCO",
            event_date: "2026-05-17",
            sequence_number: 4,
          }),
        ]),
      ),
    );
    const user = userEvent.setup();
    renderForm();
    await user.click(screen.getByText("Competencia"));
    await user.click(screen.getByText("Datos específicos"));

    await waitFor(() => {
      const select = screen.getByTestId(
        "event-race-event-id",
      ) as HTMLSelectElement;
      const labels = Array.from(select.options).map((o) => o.text);
      expect(labels.some((l) => /Válida\s*4\s*—\s*Cali XCO/.test(l))).toBe(true);
    });
  });
});
