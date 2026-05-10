import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

// ─── Mocks ───────────────────────────────────────────────────────────────────
vi.mock("@/hooks/parents/useMyAthletes");
vi.mock("@/api/calendar");

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useCalendarEvent, useRSVPEvent, useEventAttendances } from "@/api/calendar";
import { ParentEventDetailPage } from "./ParentEventDetailPage";
import type { MyAthleteOut } from "@/types/parent.types";
import { makeCalendarEventRead } from "@/test/msw/calendarHandlers";

// ─── Fixtures ─────────────────────────────────────────────────────────────────

function makeAthlete(id: number, firstName = "Sebastián"): MyAthleteOut {
  return {
    athlete_id: id,
    athlete_first_name: firstName,
    athlete_last_name: "García",
    birth_date: "2013-01-01",
    sex: "M" as any,
    age_decimal: 13.2,
    category: "U15",
    relationship: "padre" as any,
    latest_anthropometry_date: null,
    maturation_status: null,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  };
}

const noopMutation = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
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

function renderPage(eventId = "5") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/parents/calendar/events/${eventId}`]}>
        <Routes>
          <Route
            path="/parents/calendar/events/:id"
            element={<ParentEventDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useRSVPEvent).mockReturnValue(noopMutation as unknown as ReturnType<typeof useRSVPEvent>);
  vi.mocked(useEventAttendances).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useEventAttendances>);
});

// ─── Tests ────────────────────────────────────────────────────────────────────

describe("ParentEventDetailPage", () => {
  it("renderiza el título del evento como h1", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({ id: 5, title: "Copa Valle III — La Cumbre", event_type: "competition" }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderPage("5");
    expect(screen.getByRole("heading", { name: /Copa Valle III/i })).toBeInTheDocument();
  });

  it("muestra el breadcrumb con link al calendario", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({ id: 5 }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderPage("5");
    const backLink = screen.getByRole("link", { name: /Calendario/i });
    expect(backLink).toHaveAttribute("href", "/parents/calendar");
  });

  it("renderiza la descripción del evento", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({
        id: 5,
        description: "Descripción del evento de prueba",
        event_type: "club_event",
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderPage("5");
    expect(screen.getByTestId("event-description")).toHaveTextContent(
      "Descripción del evento de prueba",
    );
  });

  it("renderiza la sección de atletas del padre", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({ id: 5, event_type: "club_event" }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderPage("5");
    expect(screen.getByTestId("my-athletes-section")).toBeInTheDocument();
  });

  it("muestra skeleton de carga mientras se obtiene el evento", () => {
    (useMyAthletes as any).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderPage("5");
    // No header rendered while loading
    expect(screen.queryByTestId("event-header")).not.toBeInTheDocument();
  });

  it("muestra estado de error cuando el evento no existe", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as ReturnType<typeof useCalendarEvent>);

    renderPage("999");
    expect(screen.getByText(/Evento no encontrado/i)).toBeInTheDocument();
    expect(screen.getByText(/no existe o no tienes acceso/i)).toBeInTheDocument();
  });

  it("para training_session muestra link al detalle de sesión", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({
        id: 5,
        event_type: "training_session",
        event_data: { training_session_id: 33 },
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderPage("5");
    const link = screen.getByText(/Ver detalle del entrenamiento/i).closest("a");
    expect(link).toHaveAttribute("href", "/parents/training/sessions/33");
  });

  describe("Privacidad", () => {
    it("NO muestra coach_notes ni campos internos del entrenador", () => {
      (useMyAthletes as any).mockReturnValue({
        data: [makeAthlete(42)],
        isLoading: false,
        isError: false,
      });
      vi.mocked(useCalendarEvent).mockReturnValue({
        data: makeCalendarEventRead({ id: 5, event_type: "club_event" }),
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useCalendarEvent>);

      renderPage("5");
      expect(screen.queryByText(/Notas confidenciales del coach/i)).not.toBeInTheDocument();
      expect(screen.queryByText(/coach_notes/i)).not.toBeInTheDocument();
    });

    it("NO muestra audiencias internas (audience_type, audience_value)", () => {
      (useMyAthletes as any).mockReturnValue({
        data: [makeAthlete(42)],
        isLoading: false,
        isError: false,
      });
      vi.mocked(useCalendarEvent).mockReturnValue({
        data: makeCalendarEventRead({
          id: 5,
          event_type: "club_event",
          audiences: [{ audience_type: "all_club", audience_value: {} as Record<string, never> }],
        }),
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useCalendarEvent>);

      renderPage("5");
      expect(screen.queryByText("all_club")).not.toBeInTheDocument();
      expect(screen.queryByText("audience_type")).not.toBeInTheDocument();
    });

    it("NO muestra created_by_user_id", () => {
      (useMyAthletes as any).mockReturnValue({
        data: [makeAthlete(42)],
        isLoading: false,
        isError: false,
      });
      vi.mocked(useCalendarEvent).mockReturnValue({
        data: makeCalendarEventRead({
          id: 5,
          event_type: "club_event",
          created_by_user_id: 10,
        }),
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useCalendarEvent>);

      renderPage("5");
      expect(screen.queryByText("created_by_user_id")).not.toBeInTheDocument();
    });
  });
});
