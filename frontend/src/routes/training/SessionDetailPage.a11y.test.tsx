/**
 * Tests de accesibilidad para `SessionDetailPage` (feature 032, US2, T026):
 * `jest-axe` sin violaciones sobre la página ya sectorizada en 4 tabs
 * (Resumen/Asistencia/Plan/Media, contracts/session-sections.md).
 *
 * Sigue la convención de `ParentSessionDetailPage.a11y.test.tsx` (mismo
 * patrón de mocks + aserciones) y el set de mocks ya establecido en
 * `SessionDetailPage.test.tsx` para esta página.
 */
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSession: vi.fn(),
  useSessionAttendance: vi.fn(),
  useExecuteTrainingSession: vi.fn(),
  useCancelTrainingSession: vi.fn(),
  useUploadRouteFile: vi.fn(),
  useUpdateTrainingSession: vi.fn(),
  useUpdateAttendance: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/components/training/AttendanceTable", () => ({
  AttendanceTable: ({ attendances }: { attendances: { athlete_id: number }[] }) => (
    <div data-testid="attendance-table">Asistencia {attendances.length}</div>
  ),
}));

vi.mock("@/components/training/RouteViewer", () => ({
  RouteViewer: () => <div data-testid="route-viewer" />,
}));

vi.mock("@/components/training/MediaGallery", () => ({
  MediaGallery: () => <div data-testid="media-gallery" />,
}));

vi.mock("@/api/sessionMedia", () => ({
  useSessionMedia: () => ({ data: [], isLoading: false, isError: false }),
  useUploadSessionMedia: () => ({ mutate: vi.fn(), mutateAsync: vi.fn(), isPending: false, isError: false }),
  useDeleteSessionMedia: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/activities/useSessionActivities", () => ({
  useSessionActivities: () => ({ data: { items: [] }, isLoading: false, isError: false }),
}));

vi.mock("@/hooks/activities/useUnlinkedActivitiesNearDate", () => ({
  useUnlinkedActivitiesNearDate: () => ({
    data: { items: [], total: 0, page: 1, page_size: 30 },
    isLoading: false,
    isError: false,
  }),
}));

// PlanSection trae consigo hooks reales de intervalos que no son
// responsabilidad de este archivo — se mockea con un stub liviano.
vi.mock("@/components/training/session-plan/PlanSection", () => ({
  PlanSection: () => <div data-testid="plan-section-stub">Plan section (stub de test)</div>,
}));

import {
  useTrainingSession,
  useSessionAttendance,
  useExecuteTrainingSession,
  useCancelTrainingSession,
  useUploadRouteFile,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import { SessionDetailPage } from "./SessionDetailPage";
import type { TrainingSession, Attendance } from "@/types/trainingSession.types";

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

function makeSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 10,
    status: "planned",
    // Fecha pasada (no "hoy") — aterriza en el default "resumen" salvo que
    // el test pida otra sección explícita por `?section=`.
    scheduled_date: "2026-06-15",
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Pista XCO Buitrera",
    technical_focus: "Técnica de frenada",
    description: "Sesión de técnica básica",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function makeAttendance(): Attendance {
  return {
    id: 1,
    session_id: 1,
    athlete_id: 1,
    athlete_name: "Sebastián García",
    status: "presente",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  };
}

function renderPage(initialPath = "/training/sessions/1") {
  vi.mocked(useExecuteTrainingSession).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useExecuteTrainingSession>,
  );
  vi.mocked(useCancelTrainingSession).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useCancelTrainingSession>,
  );
  vi.mocked(useUploadRouteFile).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useUploadRouteFile>,
  );
  vi.mocked(useUpdateTrainingSession).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useUpdateTrainingSession>,
  );
  vi.mocked(useTrainingSession).mockReturnValue({
    isLoading: false,
    isError: false,
    data: makeSession(),
  } as unknown as ReturnType<typeof useTrainingSession>);
  vi.mocked(useSessionAttendance).mockReturnValue({
    data: [makeAttendance()],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useSessionAttendance>);

  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/training/sessions/:id" element={<SessionDetailPage />} />
          <Route path="/training/sessions" element={<div>Lista</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("SessionDetailPage — accesibilidad", () => {
  it("sin violaciones axe en la sección default (Resumen)", async () => {
    const { container } = renderPage();
    expect(screen.getByTestId("session-section-resumen")).toBeVisible();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe en Asistencia (?section=asistencia)", async () => {
    const { container } = renderPage("/training/sessions/1?section=asistencia");
    expect(screen.getByTestId("session-section-asistencia")).toBeVisible();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe en Plan (?section=plan)", async () => {
    const { container } = renderPage("/training/sessions/1?section=plan");
    expect(screen.getByTestId("session-section-plan")).toBeVisible();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("sin violaciones axe en Media (?section=media)", async () => {
    const { container } = renderPage("/training/sessions/1?section=media");
    expect(screen.getByTestId("session-section-media")).toBeVisible();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("los tabs de sección son accesibles por rol y nombre", () => {
    renderPage();
    expect(screen.getByRole("tablist", { name: /Secciones de la sesión/i })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Resumen" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Asistencia" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Plan" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Media" })).toBeInTheDocument();
  });
});
