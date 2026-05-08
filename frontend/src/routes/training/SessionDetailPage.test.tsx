import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

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
  RouteViewer: ({ routeFilePath }: { routeFilePath: string }) => (
    <div data-testid="route-viewer">{routeFilePath}</div>
  ),
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

function makeAttendance(overrides?: Partial<Attendance>): Attendance {
  return {
    id: 1,
    session_id: 1,
    athlete_id: 1,
    athlete_name: "Sebastián García",
    status: "presente",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage(sessionId = 1) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[`/training/sessions/${sessionId}`]}>
        <Routes>
          <Route path="/training/sessions/:id" element={<SessionDetailPage />} />
          <Route path="/training/sessions" element={<div>Lista</div>} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
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
  vi.mocked(useSessionAttendance).mockReturnValue({
    data: [makeAttendance()],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useSessionAttendance>);
});

describe("SessionDetailPage", () => {
  describe("carga", () => {
    it("muestra skeleton durante la carga", () => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: true,
        isError: false,
        data: undefined,
      } as unknown as ReturnType<typeof useTrainingSession>);
      const { container } = renderPage();
      expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
    });

    it("muestra error 404 cuando la sesión no existe", () => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: true,
        data: undefined,
      } as unknown as ReturnType<typeof useTrainingSession>);
      renderPage();
      expect(screen.getByText(/Sesión no encontrada/i)).toBeInTheDocument();
      expect(screen.getByRole("link", { name: /Volver a sesiones/i })).toBeInTheDocument();
    });
  });

  describe("sesión PLANNED", () => {
    beforeEach(() => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "planned" }),
      } as unknown as ReturnType<typeof useTrainingSession>);
    });

    it('muestra el botón "Marcar ejecutada" solo para planned', () => {
      renderPage();
      expect(screen.getByTestId("execute-session-button")).toBeInTheDocument();
    });

    it('muestra el botón "Cancelar sesión" solo para planned', () => {
      renderPage();
      expect(screen.getByTestId("cancel-session-button")).toBeInTheDocument();
    });

    it("muestra el link Editar solo para planned", () => {
      renderPage();
      const editLinks = screen.getAllByRole("link", { name: /Editar/i });
      expect(editLinks.length).toBeGreaterThanOrEqual(1);
    });

    it("ejecutar sesión llama la mutación", () => {
      const mutate = vi.fn();
      vi.mocked(useExecuteTrainingSession).mockReturnValue({
        ...mutationStub,
        mutate,
      } as unknown as ReturnType<typeof useExecuteTrainingSession>);
      renderPage();
      fireEvent.click(screen.getByTestId("execute-session-button"));
      expect(mutate).toHaveBeenCalledWith(1);
    });

    it("cancelar muestra el modal de confirmación", () => {
      renderPage();
      fireEvent.click(screen.getByTestId("cancel-session-button"));
      expect(screen.getByRole("alertdialog")).toBeInTheDocument();
      expect(screen.getByRole("alertdialog")).toHaveTextContent(/Cancelar sesión/i);
    });

    it("confirmar cancelación llama la mutación", () => {
      const mutate = vi.fn();
      vi.mocked(useCancelTrainingSession).mockReturnValue({
        ...mutationStub,
        mutate,
      } as unknown as ReturnType<typeof useCancelTrainingSession>);
      renderPage();
      fireEvent.click(screen.getByTestId("cancel-session-button"));
      fireEvent.click(screen.getByRole("button", { name: /Sí, cancelar sesión/i }));
      expect(mutate).toHaveBeenCalledWith(1, expect.any(Object));
    });
  });

  describe("sesión EXECUTED", () => {
    beforeEach(() => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "executed" }),
      } as unknown as ReturnType<typeof useTrainingSession>);
    });

    it("no muestra Marcar ejecutada cuando ya está ejecutada", () => {
      renderPage();
      expect(screen.queryByTestId("execute-session-button")).not.toBeInTheDocument();
    });

    it("no muestra botón Cancelar cuando ya está ejecutada", () => {
      renderPage();
      expect(screen.queryByTestId("cancel-session-button")).not.toBeInTheDocument();
    });
  });

  describe("sesión CANCELLED", () => {
    beforeEach(() => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "cancelled" }),
      } as unknown as ReturnType<typeof useTrainingSession>);
    });

    it("no muestra dropzone de upload cuando está cancelada", () => {
      renderPage();
      expect(screen.queryByTestId("route-upload-dropzone")).not.toBeInTheDocument();
    });
  });

  describe("upload de archivo de recorrido", () => {
    beforeEach(() => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "planned" }),
      } as unknown as ReturnType<typeof useTrainingSession>);
    });

    it("muestra el dropzone para subir archivo", () => {
      renderPage();
      expect(screen.getByTestId("route-upload-dropzone")).toBeInTheDocument();
    });

    it("llama uploadMutation al seleccionar archivo", () => {
      const mutate = vi.fn();
      vi.mocked(useUploadRouteFile).mockReturnValue({
        ...mutationStub,
        mutate,
      } as unknown as ReturnType<typeof useUploadRouteFile>);
      renderPage();
      const input = screen.getByTestId("route-file-input");
      const file = new File(["gpx content"], "ruta.gpx", { type: "application/gpx+xml" });
      Object.defineProperty(input, "files", { value: [file] });
      fireEvent.change(input);
      expect(mutate).toHaveBeenCalledWith(file);
    });
  });

  describe("asistencia", () => {
    beforeEach(() => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "planned" }),
      } as unknown as ReturnType<typeof useTrainingSession>);
    });

    it("muestra la tabla de asistencia", () => {
      renderPage();
      expect(screen.getByTestId("attendance-table")).toBeInTheDocument();
    });

    it("muestra el conteo de convocados", () => {
      renderPage();
      expect(screen.getByText(/Asistencia \(1\)/i)).toBeInTheDocument();
    });
  });
});
