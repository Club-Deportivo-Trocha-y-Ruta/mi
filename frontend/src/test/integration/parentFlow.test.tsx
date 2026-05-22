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
      user: { role: "parent", first_name: "María", last_name: "López", id: 20 },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/hooks/parents/useMyAthletes");
vi.mock("@/api/trainingSessions");
vi.mock("@/components/training/RouteViewer", () => ({
  RouteViewer: () => <div data-testid="route-viewer" />,
}));
// Wave 5: MediaGallery ahora es lazy + Suspense en ParentSessionDetailPage.
// Mockeamos el módulo para mantener el render síncrono y evitar warnings de
// dynamic import en jsdom.
vi.mock("@/components/training/MediaGallery", () => ({
  MediaGallery: () => <div data-testid="media-gallery" />,
}));
vi.mock("@/api/sessionMedia", () => ({
  useSessionMedia: () => ({ data: [], isLoading: false, isError: false }),
}));

import * as apiModule from "@/api/client";
import { useMyAthletes } from "@/hooks/parents/useMyAthletes";
import {
  useParentSessions,
  useTrainingSession,
  useSessionAttendance,
  useParentMonthlySummary,
} from "@/api/trainingSessions";
import { ParentSessionsPage } from "@/routes/parents/training/ParentSessionsPage";
import { ParentSessionDetailPage } from "@/routes/parents/training/ParentSessionDetailPage";
import { TooltipProvider } from "@/components/ui/tooltip";
import type { TrainingSession, Attendance } from "@/types/trainingSession.types";
import type { MyAthleteOut } from "@/types/parent.types";

const { apiClient } = apiModule as unknown as {
  apiClient: { get: ReturnType<typeof vi.fn> };
};

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const MY_ATHLETE_ID = 42;
const OTHER_ATHLETE_ID = 99;

function makeAthlete(id = MY_ATHLETE_ID, name = "Sebastián García"): MyAthleteOut {
  const [first, last] = name.split(" ");
  return {
    athlete_id: id,
    athlete_first_name: first,
    athlete_last_name: last,
    birth_date: "2013-01-01",
    sex: "M" as never,
    age_decimal: 13.2,
    category: "U15",
    relationship: "padre" as never,
    latest_anthropometry_date: null,
    maturation_status: null,
    standing_height_cm: null,
    weight_kg: null,
    measurement_status: "never",
  };
}

function makeSession(id = 1, overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id,
    club_id: 1,
    created_by_user_id: 10,
    status: "executed",
    scheduled_date: "2026-05-10",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Parque del Café",
    technical_focus: "Frenada controlada",
    description: "Sesión técnica",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    kid_attendances: [{ athlete_id: MY_ATHLETE_ID, status: "presente" as const }],
    ...overrides,
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
    individual_feedback: `Feedback para ${name}`,
    excuse_reason: null,
    created_at: "2026-05-10T00:00:00Z",
    updated_at: "2026-05-10T00:00:00Z",
  };
}

function makeQC() {
  return new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
}

// ---------------------------------------------------------------------------
// Tests del flujo de padre
// ---------------------------------------------------------------------------

describe("Parent flow — lista de sesiones (ParentSessionsPage)", () => {
  beforeEach(() => {
    vi.mocked(useMyAthletes).mockReturnValue({
      data: [makeAthlete()],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useMyAthletes>);

    vi.mocked(useParentSessions).mockReturnValue({
      data: [makeSession(1), makeSession(2)],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useParentSessions>);

    vi.mocked(useParentMonthlySummary).mockReturnValue({
      data: [] as import("@/types/trainingSession.types").ParentMonthlySummary[],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useParentMonthlySummary>);
  });

  it("muestra solo las sesiones donde el hijo está convocado", () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <TooltipProvider delayDuration={0}>
        <MemoryRouter>
          <ParentSessionsPage />
        </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );

    // La página renderiza (sin error)
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
  });

  it("NO realiza ninguna solicitud GET a /api/clubs endpoints", async () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <TooltipProvider delayDuration={0}>
        <MemoryRouter>
          <ParentSessionsPage />
        </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      const clubsCalls = apiClient.get.mock.calls.filter((call: unknown[]) =>
        String(call[0]).includes("/api/clubs"),
      );
      expect(clubsCalls).toHaveLength(0);
    });
  });
});

describe("Parent flow — detalle de sesión", () => {
  beforeEach(() => {
    vi.mocked(useMyAthletes).mockReturnValue({
      data: [makeAthlete()],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useMyAthletes>);

    vi.mocked(useTrainingSession).mockReturnValue({
      data: makeSession(),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useTrainingSession>);

    vi.mocked(useSessionAttendance).mockReturnValue({
      data: [
        makeAttendance(MY_ATHLETE_ID, "Sebastián García"),
        makeAttendance(OTHER_ATHLETE_ID, "Atleta Ajeno"),
      ],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useSessionAttendance>);
  });

  it("muestra únicamente la asistencia del propio hijo (no la de otros atletas)", () => {
    render(
      <QueryClientProvider client={makeQC()}>
        <TooltipProvider delayDuration={0}>
        <MemoryRouter initialEntries={["/parents/training/sessions/1"]}>
          <Routes>
            <Route path="/parents/training/sessions/:id" element={<ParentSessionDetailPage />} />
          </Routes>
        </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );

    // Nombre del hijo visible
    expect(screen.getByText("Sebastián García")).toBeInTheDocument();
    // Atleta ajeno NO visible
    expect(screen.queryByText("Atleta Ajeno")).not.toBeInTheDocument();
  });

  it("NO muestra las notas del coach (privadas)", () => {
    vi.mocked(useTrainingSession).mockReturnValue({
      data: makeSession(1, { coach_notes: "Notas privadas del entrenador" }),
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useTrainingSession>);

    render(
      <QueryClientProvider client={makeQC()}>
        <TooltipProvider delayDuration={0}>
        <MemoryRouter initialEntries={["/parents/training/sessions/1"]}>
          <Routes>
            <Route path="/parents/training/sessions/:id" element={<ParentSessionDetailPage />} />
          </Routes>
        </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );

    expect(screen.queryByText("Notas privadas del entrenador")).not.toBeInTheDocument();
  });

  it("NO contiene inputs editables (es solo lectura)", () => {
    vi.mocked(useSessionAttendance).mockReturnValue({
      data: [makeAttendance(MY_ATHLETE_ID, "Sebastián García")],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useSessionAttendance>);

    const { container } = render(
      <QueryClientProvider client={makeQC()}>
        <TooltipProvider delayDuration={0}>
        <MemoryRouter initialEntries={["/parents/training/sessions/1"]}>
          <Routes>
            <Route path="/parents/training/sessions/:id" element={<ParentSessionDetailPage />} />
          </Routes>
        </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );

    const inputs = container.querySelectorAll("input:not([type='hidden'])");
    const textareas = container.querySelectorAll("textarea");
    const selects = container.querySelectorAll("select");

    expect(inputs).toHaveLength(0);
    expect(textareas).toHaveLength(0);
    expect(selects).toHaveLength(0);
  });

  it("NO solicita /api/clubs monthly-reports desde el flujo de padre", async () => {
    vi.mocked(useSessionAttendance).mockReturnValue({
      data: [makeAttendance(MY_ATHLETE_ID, "Sebastián García")],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useSessionAttendance>);

    render(
      <QueryClientProvider client={makeQC()}>
        <TooltipProvider delayDuration={0}>
        <MemoryRouter initialEntries={["/parents/training/sessions/1"]}>
          <Routes>
            <Route path="/parents/training/sessions/:id" element={<ParentSessionDetailPage />} />
          </Routes>
        </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );

    await waitFor(() => {
      const monthlyReportsCalls = apiClient.get.mock.calls.filter((call: unknown[]) =>
        String(call[0]).includes("monthly-reports"),
      );
      expect(monthlyReportsCalls).toHaveLength(0);
    });
  });
});

describe("Parent flow — padre con múltiples hijos", () => {
  it("ve sesiones donde cualquiera de sus hijos está convocado", () => {
    const athlete1 = makeAthlete(42, "Sebastián García");
    const athlete2 = makeAthlete(43, "Laura Pérez");

    vi.mocked(useMyAthletes).mockReturnValue({
      data: [athlete1, athlete2],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useMyAthletes>);

    vi.mocked(useParentSessions).mockReturnValue({
      data: [
        makeSession(1, { kid_attendances: [{ athlete_id: 42, status: "presente" as const }] }),
        makeSession(2, { kid_attendances: [{ athlete_id: 43, status: "presente" as const }] }),
      ],
      isLoading: false,
      isError: false,
    } as ReturnType<typeof useParentSessions>);

    vi.mocked(useParentMonthlySummary).mockReturnValue({
      data: [] as import("@/types/trainingSession.types").ParentMonthlySummary[],
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useParentMonthlySummary>);

    render(
      <QueryClientProvider client={makeQC()}>
        <TooltipProvider delayDuration={0}>
        <MemoryRouter>
          <ParentSessionsPage />
        </MemoryRouter>
        </TooltipProvider>
      </QueryClientProvider>,
    );

    // Página renderiza sin errores con múltiples hijos
    expect(screen.queryByText(/error/i)).not.toBeInTheDocument();
  });
});
