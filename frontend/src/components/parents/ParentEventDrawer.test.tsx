import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";

// ─── Mocks ───────────────────────────────────────────────────────────────────
vi.mock("@/hooks/parents/useMyAthletes");
vi.mock("@/api/calendar");

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useCalendarEvent, useRSVPEvent, useEventAttendances } from "@/api/calendar";
import { ParentEventDrawer } from "./ParentEventDrawer";
import type { MyAthleteOut } from "@/types/parent.types";
import type { EventAttendanceRead } from "@/types/calendar.types";
import { makeCalendarEventRead, makeEventAttendance } from "@/test/msw/calendarHandlers";

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

interface DrawerProps {
  eventId?: number | null;
  open?: boolean;
  myAttendances?: EventAttendanceRead[];
}

function renderDrawer({ eventId = 1, open = true, myAttendances = [] }: DrawerProps = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onOpenChange = vi.fn();
  return {
    ...render(
      <QueryClientProvider client={qc}>
        <MemoryRouter>
          <ParentEventDrawer
            eventId={eventId}
            open={open}
            onOpenChange={onOpenChange}
            myAttendances={myAttendances}
          />
        </MemoryRouter>
      </QueryClientProvider>,
    ),
    onOpenChange,
  };
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

describe("ParentEventDrawer", () => {
  it("renderiza el título del evento", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({ title: "Asamblea del club", event_type: "club_event" }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer();
    expect(screen.getByTestId("drawer-title")).toHaveTextContent("Asamblea del club");
  });

  it("renderiza la descripción del evento", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({
        description: "Reunión de inicio de temporada 2026",
        event_type: "club_event",
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer();
    expect(screen.getByTestId("drawer-description")).toHaveTextContent(
      "Reunión de inicio de temporada 2026",
    );
  });

  it("muestra la sección de atletas del padre", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({ event_type: "club_event" }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer();
    expect(screen.getByTestId("my-athletes-section")).toBeInTheDocument();
  });

  it("muestra ParentRSVPInline para event_type distinto de training_session", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42, "Sebastián")],
      isLoading: false,
      isError: false,
    });
    // Evento futuro para que no esté en el pasado
    const futureDate = new Date();
    futureDate.setMonth(futureDate.getMonth() + 1);
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({
        event_type: "club_event",
        status: "scheduled",
        start_at: futureDate.toISOString(),
        end_at: new Date(futureDate.getTime() + 3600_000).toISOString(),
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer();
    // ParentRSVPInline renders 3 buttons
    expect(screen.getByRole("button", { name: /Aceptar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Declinar/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Tentativo/i })).toBeInTheDocument();
  });

  it("muestra link a página de sesión para event_type=training_session con ID", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });
    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({
        event_type: "training_session",
        event_data: { training_session_id: 77 },
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer();
    const link = screen.getByText(/Ver detalle del entrenamiento/i).closest("a");
    expect(link).toHaveAttribute("href", "/parents/training/sessions/77");
  });

  it("el botón 'Ver detalle completo' navega a la ruta correcta", () => {
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

    renderDrawer({ eventId: 5 });
    const link = screen.getByTestId("view-detail-link");
    expect(link).toHaveAttribute("href", "/parents/calendar/events/5");
  });

  it("muestra skeleton de carga", () => {
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

    renderDrawer();
    // Drawer renderiza skeleton cuando carga — title no visible
    expect(screen.queryByTestId("drawer-title")).not.toBeInTheDocument();
  });

  it("muestra mensaje de error si falla la carga", () => {
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

    renderDrawer();
    expect(screen.getByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/No se pudo cargar el detalle/i)).toBeInTheDocument();
  });

  // ── Privacidad ──────────────────────────────────────────────────────────────

  describe("Privacidad — el padre NO ve datos de otros atletas", () => {
    it("filtra attendances: solo muestra las de los atletas del padre", () => {
      const myAthleteId = 42;
      const otherAthleteId = 999;

      (useMyAthletes as any).mockReturnValue({
        data: [makeAthlete(myAthleteId, "Sebastián")],
        isLoading: false,
        isError: false,
      });
      vi.mocked(useCalendarEvent).mockReturnValue({
        data: makeCalendarEventRead({ event_type: "club_event" }),
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useCalendarEvent>);

      // Pasa attendances que incluyen OTRO atleta — el componente debe filtrarlas
      const myAttendance = makeEventAttendance({ athlete_id: myAthleteId, rsvp_status: "accepted" });
      const otherAttendance = makeEventAttendance({ id: 2, athlete_id: otherAthleteId, rsvp_status: "declined" });

      renderDrawer({ myAttendances: [myAttendance, otherAttendance] });

      // La sección de atletas del padre sólo debe mostrar los chips del propio atleta
      const section = screen.getByTestId("my-athletes-section");
      expect(section).toBeInTheDocument();

      // athlete_id=42 tiene badge "Aceptado"
      expect(screen.getByTestId(`rsvp-badge-${myAthleteId}`)).toHaveTextContent("Aceptado");
      // athlete_id=999 NO debe renderizarse (no es hijo del padre)
      expect(screen.queryByTestId(`rsvp-badge-${otherAthleteId}`)).not.toBeInTheDocument();
    });

    it("NO renderiza 'coach_notes' (campo privado del entrenador)", () => {
      (useMyAthletes as any).mockReturnValue({
        data: [makeAthlete(42)],
        isLoading: false,
        isError: false,
      });
      vi.mocked(useCalendarEvent).mockReturnValue({
        // EventRead del backend NO contiene extended_props (eso es de EventListItem).
        // Aún así verificamos que el drawer no muestra ningún campo privado.
        data: makeCalendarEventRead({ event_type: "club_event" }),
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useCalendarEvent>);

      renderDrawer();
      expect(screen.queryByText("Notas privadas del entrenador")).not.toBeInTheDocument();
      expect(screen.queryByText(/coach_notes/i)).not.toBeInTheDocument();
    });

    it("NO renderiza 'audiencias internas' del evento", () => {
      (useMyAthletes as any).mockReturnValue({
        data: [makeAthlete(42)],
        isLoading: false,
        isError: false,
      });
      vi.mocked(useCalendarEvent).mockReturnValue({
        data: makeCalendarEventRead({
          event_type: "club_event",
          audiences: [{ audience_type: "all_club", audience_value: {} as Record<string, never> }],
        }),
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useCalendarEvent>);

      renderDrawer();
      expect(screen.queryByText("all_club")).not.toBeInTheDocument();
      expect(screen.queryByText("audience_type")).not.toBeInTheDocument();
      expect(screen.queryByText("audience_value")).not.toBeInTheDocument();
    });

    it("NO renderiza 'created_by_user_id' (dato interno del sistema)", () => {
      (useMyAthletes as any).mockReturnValue({
        data: [makeAthlete(42)],
        isLoading: false,
        isError: false,
      });
      vi.mocked(useCalendarEvent).mockReturnValue({
        data: makeCalendarEventRead({ event_type: "club_event", created_by_user_id: 10 }),
        isLoading: false,
        isError: false,
      } as ReturnType<typeof useCalendarEvent>);

      renderDrawer();
      expect(screen.queryByText("created_by_user_id")).not.toBeInTheDocument();
      expect(screen.queryByText("10")).not.toBeInTheDocument();
    });
  });

  it("deshabilita RSVP si el evento está en el pasado", () => {
    (useMyAthletes as any).mockReturnValue({
      data: [makeAthlete(42)],
      isLoading: false,
      isError: false,
    });

    const pastDate = new Date();
    pastDate.setMonth(pastDate.getMonth() - 1);

    vi.mocked(useCalendarEvent).mockReturnValue({
      data: makeCalendarEventRead({
        event_type: "club_event",
        status: "completed",
        start_at: pastDate.toISOString(),
        end_at: new Date(pastDate.getTime() + 3600_000).toISOString(),
      }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useCalendarEvent>);

    renderDrawer();
    // RSVP buttons should NOT be present for past events
    expect(screen.queryByRole("button", { name: /Aceptar/i })).not.toBeInTheDocument();
  });
});
