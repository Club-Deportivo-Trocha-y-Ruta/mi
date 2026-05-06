import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/hooks/parents/useMyAthletes");
vi.mock("@/api/trainingSessions");
vi.mock("@/components/training/RouteViewer", () => ({
  RouteViewer: () => <div data-testid="route-viewer" />,
}));

import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import { useTrainingSession, useSessionAttendance } from "@/api/trainingSessions";
import { ParentSessionDetailPage } from "./ParentSessionDetailPage";
import type { Attendance, TrainingSession } from "@/types/trainingSession.types";
import type { MyAthleteOut } from "@/types/parent.types";

const MY_ATHLETE_ID = 42;
const OTHER_ATHLETE_ID_A = 77;
const OTHER_ATHLETE_ID_B = 88;

function makeAthlete(): MyAthleteOut {
  return {
    athlete_id: MY_ATHLETE_ID,
    athlete_first_name: "Sebastián",
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

function makeSession(): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 2,
    age_group: "u15",
    status: "executed",
    scheduled_date: "2026-05-10",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Parque del Café",
    technical_focus: "Frenada controlada",
    description: "Sesión de técnica básica",
    coach_notes: "Notas internas del coach — NO para padres",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  };
}

function makeAttendance(athleteId: number, name: string): Attendance {
  return {
    id: athleteId,
    session_id: 1,
    athlete_id: athleteId,
    athlete_name: name,
    status: "presente",
    rpe_omni: 7,
    rubric_effort: 4,
    rubric_attitude: 5,
    rubric_technique: 3,
    individual_feedback: `Comentario para ${name}`,
    created_at: "2026-05-10T00:00:00Z",
    updated_at: "2026-05-10T00:00:00Z",
  };
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: false } },
});

function renderPage(sessionId = 1) {
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/parents/training/sessions/${sessionId}`]}>
        <Routes>
          <Route
            path="/parents/training/sessions/:id"
            element={<ParentSessionDetailPage />}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  queryClient.clear();

  (useMyAthletes as any).mockReturnValue({
    data: [makeAthlete()],
    isLoading: false,
    isError: false,
  });

  (useTrainingSession as any).mockReturnValue({
    data: makeSession(),
    isLoading: false,
    isError: false,
  });
});

describe("ParentSessionDetailPage — privacidad (CRÍTICO)", () => {
  it("muestra solo la fila de asistencia del atleta del padre aunque la API devuelva 3 filas", () => {
    // API response leaks 3 attendance rows (1 belongs to parent's kid)
    const leaked: Attendance[] = [
      makeAttendance(MY_ATHLETE_ID, "Sebastián García"),
      makeAttendance(OTHER_ATHLETE_ID_A, "Nombre Ajeno A"),
      makeAttendance(OTHER_ATHLETE_ID_B, "Nombre Ajeno B"),
    ];

    (useSessionAttendance as any).mockReturnValue({
      data: leaked,
      isLoading: false,
      isError: false,
    });

    const { container } = renderPage();

    // Solo 1 fila con data-athlete-id del hijo del padre
    const myRows = container.querySelectorAll(`[data-athlete-id='${MY_ATHLETE_ID}']`);
    const otherA = container.querySelectorAll(`[data-athlete-id='${OTHER_ATHLETE_ID_A}']`);
    const otherB = container.querySelectorAll(`[data-athlete-id='${OTHER_ATHLETE_ID_B}']`);

    expect(myRows.length).toBe(1);
    expect(otherA.length).toBe(0);
    expect(otherB.length).toBe(0);
  });

  it("nunca muestra el nombre de otros atletas en el DOM", () => {
    const leaked: Attendance[] = [
      makeAttendance(MY_ATHLETE_ID, "Sebastián García"),
      makeAttendance(OTHER_ATHLETE_ID_A, "Nombre Ajeno A"),
      makeAttendance(OTHER_ATHLETE_ID_B, "Nombre Ajeno B"),
    ];

    (useSessionAttendance as any).mockReturnValue({
      data: leaked,
      isLoading: false,
      isError: false,
    });

    renderPage();

    expect(screen.queryByText("Nombre Ajeno A")).not.toBeInTheDocument();
    expect(screen.queryByText("Nombre Ajeno B")).not.toBeInTheDocument();
    expect(screen.getByText("Sebastián García")).toBeInTheDocument();
  });

  it("no muestra coach_notes aunque vengan en la respuesta de la sesión", () => {
    (useSessionAttendance as any).mockReturnValue({
      data: [makeAttendance(MY_ATHLETE_ID, "Sebastián García")],
      isLoading: false,
      isError: false,
    });

    renderPage();

    // coach_notes contiene "Notas internas del coach — NO para padres"
    expect(
      screen.queryByText("Notas internas del coach — NO para padres"),
    ).not.toBeInTheDocument();
  });

  it("no contiene inputs editables", () => {
    (useSessionAttendance as any).mockReturnValue({
      data: [makeAttendance(MY_ATHLETE_ID, "Sebastián García")],
      isLoading: false,
      isError: false,
    });

    const { container } = renderPage();

    // No inputs, no textarea, no select (todo es lectura)
    const inputs = container.querySelectorAll("input:not([type='hidden'])");
    const textareas = container.querySelectorAll("textarea");
    const selects = container.querySelectorAll("select");

    expect(inputs).toHaveLength(0);
    expect(textareas).toHaveLength(0);
    expect(selects).toHaveLength(0);
  });

  it("muestra mensaje cuando el atleta no está convocado", () => {
    (useSessionAttendance as any).mockReturnValue({
      data: [makeAttendance(OTHER_ATHLETE_ID_A, "Otro Atleta")],
      isLoading: false,
      isError: false,
    });

    renderPage();

    expect(
      screen.getByText(/Tu atleta no figura como convocado/),
    ).toBeInTheDocument();
  });

  it("muestra info general de la sesión (foco técnico, lugar)", () => {
    (useSessionAttendance as any).mockReturnValue({
      data: [makeAttendance(MY_ATHLETE_ID, "Sebastián García")],
      isLoading: false,
      isError: false,
    });

    renderPage();

    expect(screen.getByText("Frenada controlada")).toBeInTheDocument();
    expect(screen.getAllByText("Parque del Café").length).toBeGreaterThan(0);
  });

  it("muestra estado 'Sin comentario aún' cuando el feedback está vacío", () => {
    (useSessionAttendance as any).mockReturnValue({
      data: [
        makeAttendance(MY_ATHLETE_ID, "Sebastián García"),
      ].map((a) => ({ ...a, individual_feedback: null })),
      isLoading: false,
      isError: false,
    });

    renderPage();

    expect(screen.getByText("Sin comentario aún.")).toBeInTheDocument();
  });
});
