import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — todos antes de importar componentes
// ---------------------------------------------------------------------------

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "Test", id: 10 },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/store/trainingFiltersStore", () => ({
  useTrainingFiltersStore: vi.fn(),
}));

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
  useTrainingSession: vi.fn(),
  useSessionAttendance: vi.fn(),
  useCreateTrainingSession: vi.fn(),
  useExecuteTrainingSession: vi.fn(),
  useCancelTrainingSession: vi.fn(),
  useUpdateTrainingSession: vi.fn(),
  useUpdateAttendance: vi.fn(),
  useUploadRouteFile: vi.fn(),
}));

vi.mock("@/components/training/SessionFiltersBar", () => ({
  SessionFiltersBar: () => <div data-testid="filters-bar" />,
}));

vi.mock("@/components/training/AthletesMultiSelect", () => ({
  AthletesMultiSelect: ({ onChange }: { onChange: (ids: number[]) => void }) => (
    <button type="button" data-testid="athletes-select" onClick={() => onChange([42, 43])}>
      Seleccionar atletas
    </button>
  ),
}));

vi.mock("@/components/training/AttendanceTable", () => ({
  AttendanceTable: ({ attendances }: { attendances: { athlete_id: number }[] }) => (
    <div data-testid="attendance-table">Asistencia ({attendances.length})</div>
  ),
}));

vi.mock("@/components/training/RouteViewer", () => ({
  RouteViewer: () => <div data-testid="route-viewer" />,
}));

vi.mock("@/components/training/SessionsTable", () => ({
  SessionsTable: ({
    items,
    onExecute,
  }: {
    items: { id: number; technical_focus: string; status: string }[];
    onExecute?: (id: number) => void;
  }) => (
    <div data-testid="sessions-table">
      {items.map((s) => (
        <div key={s.id} data-testid={`session-row-${s.id}`}>
          <span>{s.technical_focus}</span>
          <span data-testid={`status-${s.id}`}>{s.status}</span>
          {s.status === "planned" && onExecute && (
            <button type="button" onClick={() => onExecute(s.id)}>
              Ejecutar
            </button>
          )}
        </div>
      ))}
    </div>
  ),
}));

import * as apiModule from "@/api/client";
import {
  useTrainingSessions,
  useTrainingSession,
  useSessionAttendance,
  useCreateTrainingSession,
  useExecuteTrainingSession,
  useCancelTrainingSession,
  useUpdateTrainingSession,
  useUpdateAttendance,
  useUploadRouteFile,
} from "@/api/trainingSessions";
import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import { SessionsListPage } from "@/routes/training/SessionsListPage";
import { SessionDetailPage } from "@/routes/training/SessionDetailPage";
import type { TrainingSession, Attendance } from "@/types/trainingSession.types";

const { apiClient } = apiModule as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    patch: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 10,
    age_group: "u15",
    status: "planned",
    scheduled_date: "2026-05-15",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Pista XCO",
    technical_focus: "Técnica de frenada",
    description: "Sesión de frenada",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function makeAttendance(athleteId = 42): Attendance {
  return {
    id: athleteId,
    session_id: 1,
    athlete_id: athleteId,
    athlete_name: "Sebastián García",
    status: "presente",
    rpe_omni: 6,
    rubric_effort: 4,
    rubric_attitude: 3,
    rubric_technique: 5,
    individual_feedback: null,
    excuse_reason: null,
    created_at: "2026-05-15T00:00:00Z",
    updated_at: "2026-05-15T00:00:00Z",
  };
}

const mutationStub = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isIdle: true,
  isSuccess: false,
  isError: false,
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

const defaultFilters = {
  from_date: "2026-05-01",
  to_date: "2026-05-31",
  age_group: "" as const,
  status: "" as const,
  setFromDate: vi.fn(),
  setToDate: vi.fn(),
  setAgeGroup: vi.fn(),
  setStatus: vi.fn(),
  resetToCurrentMonth: vi.fn(),
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

function setupMocks(sessions: TrainingSession[], session?: TrainingSession, attendances?: Attendance[]) {
  vi.mocked(useTrainingFiltersStore).mockReturnValue(defaultFilters as ReturnType<typeof useTrainingFiltersStore>);
  vi.mocked(useTrainingSessions).mockReturnValue({ data: sessions, isLoading: false, isError: false } as ReturnType<typeof useTrainingSessions>);
  vi.mocked(useTrainingSession).mockReturnValue({ data: session, isLoading: false, isError: !session } as ReturnType<typeof useTrainingSession>);
  vi.mocked(useSessionAttendance).mockReturnValue({ data: attendances ?? [], isLoading: false, isError: false } as ReturnType<typeof useSessionAttendance>);
  vi.mocked(useCreateTrainingSession).mockReturnValue(mutationStub as unknown as ReturnType<typeof useCreateTrainingSession>);
  vi.mocked(useExecuteTrainingSession).mockReturnValue(mutationStub as unknown as ReturnType<typeof useExecuteTrainingSession>);
  vi.mocked(useCancelTrainingSession).mockReturnValue(mutationStub as unknown as ReturnType<typeof useCancelTrainingSession>);
  vi.mocked(useUpdateTrainingSession).mockReturnValue(mutationStub as unknown as ReturnType<typeof useUpdateTrainingSession>);
  vi.mocked(useUpdateAttendance).mockReturnValue(mutationStub as unknown as ReturnType<typeof useUpdateAttendance>);
  vi.mocked(useUploadRouteFile).mockReturnValue(mutationStub as unknown as ReturnType<typeof useUploadRouteFile>);
}

// ---------------------------------------------------------------------------
// Tests del flujo del coach
// ---------------------------------------------------------------------------

describe("Coach flow — lista de sesiones", () => {
  beforeEach(() => {
    setupMocks([makeSession(), makeSession({ id: 2, status: "executed", technical_focus: "Saltos básicos" })]);
  });

  it("lista las sesiones planificadas del club", () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter>
          <SessionsListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByTestId("sessions-table")).toBeInTheDocument();
    expect(screen.getByText("Técnica de frenada")).toBeInTheDocument();
    expect(screen.getByText("Saltos básicos")).toBeInTheDocument();
  });

  it("muestra botón para crear nueva sesión", () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter>
          <SessionsListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByRole("link", { name: /Nueva sesión/i })).toBeInTheDocument();
  });
});

describe("Coach flow — detalle de sesión", () => {
  beforeEach(() => {
    setupMocks(
      [makeSession()],
      makeSession({ id: 1, status: "planned" }),
      [makeAttendance(42), makeAttendance(43)],
    );
  });

  it("muestra el foco técnico y la tabla de asistencia", () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter initialEntries={["/training/sessions/1"]}>
          <Routes>
            <Route path="/training/sessions/:id" element={<SessionDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.getByText("Técnica de frenada")).toBeInTheDocument();
    expect(screen.getByTestId("attendance-table")).toBeInTheDocument();
  });

  it("la tabla de asistencia muestra el número de convocados", () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter initialEntries={["/training/sessions/1"]}>
          <Routes>
            <Route path="/training/sessions/:id" element={<SessionDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Multiple elements may match — use getAllByText and check at least one exists
    const elements = screen.getAllByText(/Asistencia \(2\)/i);
    expect(elements.length).toBeGreaterThanOrEqual(1);
  });

  it("muestra el botón de ejecutar para sesión planificada", () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter initialEntries={["/training/sessions/1"]}>
          <Routes>
            <Route path="/training/sessions/:id" element={<SessionDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    // Use data-testid as per SessionDetailPage implementation
    expect(screen.getByTestId("execute-session-button")).toBeInTheDocument();
  });
});

describe("Coach flow — sesión ejecutada no permite editar", () => {
  it("oculta el botón de ejecutar cuando la sesión ya está executed", () => {
    setupMocks(
      [makeSession({ status: "executed" })],
      makeSession({ id: 1, status: "executed" }),
      [makeAttendance()],
    );

    render(
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter initialEntries={["/training/sessions/1"]}>
          <Routes>
            <Route path="/training/sessions/:id" element={<SessionDetailPage />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    expect(screen.queryByTestId("execute-session-button")).not.toBeInTheDocument();
  });
});

describe("Coach flow — requests HTTP esperados", () => {
  it("no llama a /api/clubs endpoints desde la vista de lista", async () => {
    setupMocks([makeSession()]);

    render(
      <QueryClientProvider client={makeQC()}>
        <MemoryRouter>
          <SessionsListPage />
        </MemoryRouter>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      const clubsCallsFromGet = apiClient.get.mock.calls.filter((call: unknown[]) =>
        String(call[0]).includes("/api/clubs"),
      );
      expect(clubsCallsFromGet).toHaveLength(0);
    });
  });
});
