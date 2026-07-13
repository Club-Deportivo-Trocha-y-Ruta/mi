import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import {
  createMemoryRouter,
  MemoryRouter,
  Route,
  RouterProvider,
  Routes,
} from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { AgeGateDialog } from "@/components/intervals/AgeGateDialog";
import { todayISODate } from "@/lib/datetime";

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

// Ambos hooks reales de actividades corren contra `apiClient.get` mockeado
// (retorna `undefined`), lo que los deja "pending" indefinidamente y puede
// disparar un act()/unhandled-rejection warning silencioso — se mockean
// explícitamente, mismo patrón que el resto de hooks de la página
// (session-detail-redesign.md §8).
vi.mock("@/hooks/activities/useSessionActivities", () => ({
  useSessionActivities: vi.fn(),
}));

vi.mock("@/hooks/activities/useUnlinkedActivitiesNearDate", () => ({
  useUnlinkedActivitiesNearDate: vi.fn(),
}));

// PlanSection (feature 032, US1) trae consigo hooks reales de técnica/fuerza/
// intervalos (useSessionExercises, useSessionBlocks, useSessionStructure…)
// que no son responsabilidad de este archivo — se mockea con un stub que
// incluye un `AgeGateDialog` real y siempre abierto para la aserción de
// regresión de T025 (SC-007: el diálogo debe seguir abriendo igual desde
// dentro del contenedor de tabs nuevo).
vi.mock("@/components/training/session-plan/PlanSection", () => ({
  PlanSection: () => (
    <div data-testid="plan-section-stub">
      <p>Plan section (stub de test)</p>
      <AgeGateDialog
        open
        onOpenChange={() => {}}
        mode="confirmation"
        targetAgeBand="10-12"
        onConfirm={() => {}}
        isPending={false}
      />
    </div>
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
import { useSessionActivities } from "@/hooks/activities/useSessionActivities";
import { useUnlinkedActivitiesNearDate } from "@/hooks/activities/useUnlinkedActivitiesNearDate";
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

function renderPage(sessionId = 1, initialPath?: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[initialPath ?? `/training/sessions/${sessionId}`]}>
        <Routes>
          <Route path="/training/sessions/:id" element={<SessionDetailPage />} />
          <Route path="/training/sessions" element={<div>Lista</div>} />
          <Route
            path="/training/sessions/:id/activity-match/:activityId"
            element={<div data-testid="activity-match-page-stub">Comparación plan vs. real</div>}
          />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

/**
 * Variante con `createMemoryRouter`/`RouterProvider` (data router) para los
 * tests que necesitan navegación "atrás" real (`router.navigate(-1)`) —
 * `MemoryRouter` declarativo no expone un history programático equivalente.
 */
function renderPageWithHistory(initialPath: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter(
    [
      { path: "/training/sessions/:id", element: <SessionDetailPage /> },
      { path: "/training/sessions", element: <div>Lista</div> },
    ],
    { initialEntries: [initialPath] },
  );
  render(
    <QueryClientProvider client={qc}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  return router;
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
  vi.mocked(useSessionActivities).mockReturnValue({
    data: { items: [] },
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useSessionActivities>);
  vi.mocked(useUnlinkedActivitiesNearDate).mockReturnValue({
    data: { items: [], total: 0, page: 1, page_size: 30 },
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useUnlinkedActivitiesNearDate>);
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
      // El nuevo diálogo pregunta si avisar a los padres de la cancelación.
      expect(screen.getByRole("alertdialog")).toHaveTextContent(/cancelación/i);
    });

    it("confirmar cancelación con 'Enviar notificación' llama la mutación con notify=true", () => {
      const mutate = vi.fn();
      vi.mocked(useCancelTrainingSession).mockReturnValue({
        ...mutationStub,
        mutate,
      } as unknown as ReturnType<typeof useCancelTrainingSession>);
      renderPage();
      fireEvent.click(screen.getByTestId("cancel-session-button"));
      fireEvent.click(screen.getByRole("button", { name: /Enviar notificación/i }));
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({ id: 1, notify: true }),
        expect.any(Object),
      );
    });

    it("confirmar cancelación con 'No enviar' llama la mutación con notify=false", () => {
      const mutate = vi.fn();
      vi.mocked(useCancelTrainingSession).mockReturnValue({
        ...mutationStub,
        mutate,
      } as unknown as ReturnType<typeof useCancelTrainingSession>);
      renderPage();
      fireEvent.click(screen.getByTestId("cancel-session-button"));
      fireEvent.click(screen.getByRole("button", { name: /No enviar/i }));
      expect(mutate).toHaveBeenCalledWith(
        expect.objectContaining({ id: 1, notify: false }),
        expect.any(Object),
      );
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

    // La sesión de fixture (2026-06-15) no es "hoy" — la sección Asistencia
    // no es el default (feature 032/US2), así que estos tests la piden
    // explícita por `?section=` en vez de depender de la regla default.
    it("muestra la tabla de asistencia", () => {
      renderPage(1, "/training/sessions/1?section=asistencia");
      expect(screen.getByTestId("attendance-table")).toBeInTheDocument();
    });

    it("muestra el conteo de convocados", () => {
      renderPage(1, "/training/sessions/1?section=asistencia");
      expect(screen.getByText(/Asistencia \(1\)/i)).toBeInTheDocument();
    });

    it("ya no renderiza la sección separada 'Actividades Strava' (fusionada en la fila de asistencia)", () => {
      renderPage(1, "/training/sessions/1?section=asistencia");
      expect(screen.queryByText(/^Actividades Strava$/i)).not.toBeInTheDocument();
      expect(screen.queryByTestId("session-activities-groups")).not.toBeInTheDocument();
      expect(screen.queryByTestId("session-activities-empty")).not.toBeInTheDocument();
    });

    it("muestra la nota de error inline cuando fallan las actividades Strava de la sesión", () => {
      vi.mocked(useSessionActivities).mockReturnValue({
        data: undefined,
        isLoading: false,
        isError: true,
      } as unknown as ReturnType<typeof useSessionActivities>);
      renderPage(1, "/training/sessions/1?section=asistencia");
      expect(
        screen.getByText(/No se pudieron cargar las actividades Strava vinculadas/i),
      ).toBeInTheDocument();
    });
  });

  // ---------------------------------------------------------------------
  // Secciones (?section=) — feature 032, US2 (contracts/session-sections.md)
  // ---------------------------------------------------------------------
  describe("secciones (?section=)", () => {
    const ALL_SECTION_TESTIDS = [
      "session-section-resumen",
      "session-section-asistencia",
      "session-section-plan",
      "session-section-media",
    ];

    beforeEach(() => {
      // Fecha pasada (no "hoy") — el default cae en "resumen" salvo que el
      // test la pida explícita por `?section=`.
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "planned", scheduled_date: "2026-06-15" }),
      } as unknown as ReturnType<typeof useTrainingSession>);
    });

    it.each([
      ["resumen", "session-section-resumen"],
      ["asistencia", "session-section-asistencia"],
      ["plan", "session-section-plan"],
      ["media", "session-section-media"],
    ])("?section=%s renderiza esa sección y oculta las otras tres", (section, testId) => {
      renderPage(1, `/training/sessions/1?section=${section}`);
      expect(screen.getByTestId(testId)).toBeVisible();
      for (const otherTestId of ALL_SECTION_TESTIDS) {
        if (otherTestId === testId) continue;
        // `@radix-ui/react-tabs` mantiene los `TabsContent` inactivos
        // montados en el DOM (ocultos vía atributo `hidden`, no
        // desmontados) — se verifica visibilidad, no presencia.
        expect(screen.getByTestId(otherTestId)).not.toBeVisible();
      }
    });

    it("un valor de ?section= desconocido/inválido cae al default (resumen, sesión no es hoy)", () => {
      renderPage(1, "/training/sessions/1?section=no-existe");
      expect(screen.getByTestId("session-section-resumen")).toBeVisible();
      expect(screen.getByTestId("session-section-asistencia")).not.toBeVisible();
    });

    it("sin ?section=, una sesión de HOY tiene default 'asistencia'", () => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "planned", scheduled_date: todayISODate() }),
      } as unknown as ReturnType<typeof useTrainingSession>);
      renderPage(1, "/training/sessions/1");
      expect(screen.getByTestId("session-section-asistencia")).toBeVisible();
      expect(screen.getByTestId("session-section-resumen")).not.toBeVisible();
    });

    it("sin ?section=, una sesión FUTURA tiene default 'resumen'", () => {
      vi.mocked(useTrainingSession).mockReturnValue({
        isLoading: false,
        isError: false,
        data: makeSession({ status: "planned", scheduled_date: "2099-01-01" }),
      } as unknown as ReturnType<typeof useTrainingSession>);
      renderPage(1, "/training/sessions/1");
      expect(screen.getByTestId("session-section-resumen")).toBeVisible();
      expect(screen.getByTestId("session-section-asistencia")).not.toBeVisible();
    });

    it("un click explícito en un tab agrega una entrada de historial; 'atrás' vuelve a la sección anterior sin salir de la página", async () => {
      const user = userEvent.setup();
      const router = renderPageWithHistory("/training/sessions/1");

      // Default (replace) aterriza en "resumen" — la sesión de fixture no es hoy.
      await waitFor(() => {
        expect(screen.getByTestId("session-section-resumen")).toBeInTheDocument();
      });

      await user.click(screen.getByTestId("session-section-tab-asistencia"));
      expect(screen.getByTestId("session-section-asistencia")).toBeInTheDocument();

      await router.navigate(-1);

      await waitFor(() => {
        expect(screen.getByTestId("session-section-resumen")).toBeInTheDocument();
      });
      // Seguimos en la misma página — "atrás" no salió de la sesión.
      expect(screen.getByTestId("session-detail-header")).toBeInTheDocument();
    });

    it("un remount simulado con la misma URL preserva la sección activa", () => {
      const { unmount } = renderPage(1, "/training/sessions/1?section=media");
      expect(screen.getByTestId("session-section-media")).toBeInTheDocument();
      unmount();

      renderPage(1, "/training/sessions/1?section=media");
      expect(screen.getByTestId("session-section-media")).toBeInTheDocument();
    });

    it("montar directo con ?section=plan renderiza Plan activo sin necesidad de click", () => {
      renderPage(1, "/training/sessions/1?section=plan");
      expect(screen.getByTestId("session-section-plan")).toBeInTheDocument();
      expect(screen.getByTestId("plan-section-stub")).toBeInTheDocument();
    });

    it("la ruta separada /training/sessions/{id}/activity-match/{activityId} no se ve afectada por la sectorización (FR-008)", () => {
      renderPage(1, "/training/sessions/1/activity-match/55");
      expect(screen.getByTestId("activity-match-page-stub")).toBeInTheDocument();
      expect(screen.queryByTestId("session-section-tab-resumen")).not.toBeInTheDocument();
      expect(screen.queryByTestId("session-detail-header")).not.toBeInTheDocument();
    });

    it("regresión SC-007: AgeGateDialog sigue abriendo igual desde el bloque de intervalos ahora dentro de PlanSection", () => {
      renderPage(1, "/training/sessions/1?section=plan");
      expect(
        screen.getByRole("heading", { name: "Confirmá la estructura para esta categoría" }),
      ).toBeInTheDocument();
    });
  });
});
