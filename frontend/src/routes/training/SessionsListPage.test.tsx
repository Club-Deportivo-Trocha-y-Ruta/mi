import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn(), delete: vi.fn(), interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } } },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
  useExecuteTrainingSession: vi.fn(),
  useCancelTrainingSession: vi.fn(),
}));

vi.mock("@/store/trainingFiltersStore", () => ({
  useTrainingFiltersStore: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) => sel({ accessToken: "tok", user: { role: "coach", first_name: "Juan", last_name: "Test" }, isAuthenticated: true })),
}));

vi.mock("@/components/training/SessionFiltersBar", () => ({
  SessionFiltersBar: () => <div data-testid="filters-bar">Filtros</div>,
}));

vi.mock("@/components/training/SessionsTable", () => ({
  SessionsTable: ({
    items,
    onExecute,
    onCancel,
  }: {
    items: { id: number; technical_focus: string }[];
    onExecute?: (id: number) => void;
    onCancel?: (id: number) => void;
  }) => (
    <div data-testid="sessions-table">
      {items.map((s) => (
        <div key={s.id}>
          {s.technical_focus}
          {onExecute && (
            <button onClick={() => onExecute(s.id)}>Ejecutar-{s.id}</button>
          )}
          {onCancel && (
            <button onClick={() => onCancel(s.id)}>Cancelar-{s.id}</button>
          )}
        </div>
      ))}
    </div>
  ),
}));

vi.mock("@/components/shared/ConfirmDialog", () => ({
  ConfirmDialog: ({
    open,
    title,
    onConfirm,
    onCancel,
  }: {
    open: boolean;
    title: string;
    onConfirm: () => void;
    onCancel: () => void;
  }) =>
    open ? (
      <div data-testid="confirm-dialog">
        <span>{title}</span>
        <button onClick={onConfirm}>confirm-ok</button>
        <button onClick={onCancel}>confirm-cancel</button>
      </div>
    ) : null,
}));

vi.mock("@/components/training/NotifyParentsDialog", () => ({
  NotifyParentsDialog: ({
    open,
    onSend,
    onSkip,
    onCancel,
  }: {
    open: boolean;
    onSend: (reason?: string) => void;
    onSkip: () => void;
    onCancel: () => void;
  }) =>
    open ? (
      <div data-testid="confirm-modal">
        <span>Cancelar sesión</span>
        <button onClick={() => onSend()}>confirm-ok</button>
        <button onClick={onSkip}>confirm-skip</button>
        <button onClick={onCancel}>confirm-cancel</button>
      </div>
    ) : null,
}));

import {
  useTrainingSessions,
  useExecuteTrainingSession,
  useCancelTrainingSession,
} from "@/api/trainingSessions";
import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import { SessionsListPage } from "./SessionsListPage";
import type { TrainingSession } from "@/types/trainingSession.types";

const defaultFilters = {
  from_date: "2026-05-01",
  to_date: "2026-05-31",
  status: "" as const,
  setFromDate: vi.fn(),
  setToDate: vi.fn(),
  setStatus: vi.fn(),
  resetToCurrentMonth: vi.fn(),
};

const mutationStub = { mutate: vi.fn(), isPending: false, mutateAsync: vi.fn(), reset: vi.fn(), isIdle: true, isSuccess: false, isError: false, data: undefined, error: null, variables: undefined, context: undefined, status: "idle", failureCount: 0, failureReason: null, submittedAt: 0 };

function makeSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 10,
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

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SessionsListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.mocked(useTrainingFiltersStore).mockReturnValue(defaultFilters);
  vi.mocked(useExecuteTrainingSession).mockReturnValue(mutationStub as unknown as ReturnType<typeof useExecuteTrainingSession>);
  vi.mocked(useCancelTrainingSession).mockReturnValue(mutationStub as unknown as ReturnType<typeof useCancelTrainingSession>);
});

describe("SessionsListPage", () => {
  it("muestra skeleton durante la carga", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    } as unknown as ReturnType<typeof useTrainingSessions>);
    const { container } = renderPage();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("muestra error cuando falla la carga", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
      refetch: vi.fn(),
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();
    expect(screen.getByText(/No se pudo cargar la lista de sesiones/i)).toBeInTheDocument();
  });

  it("reintenta la consulta de sesiones al pulsar 'Reintentar'", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
      refetch,
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();

    const retryButton = screen.getByRole("button", { name: /Reintentar/i });
    await user.click(retryButton);

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("muestra estado vacío cuando no hay sesiones", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();
    expect(screen.getByText(/No hay sesiones para los filtros seleccionados/i)).toBeInTheDocument();
  });

  it("muestra la tabla con sesiones cuando hay datos", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [makeSession()],
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();
    expect(screen.getByTestId("sessions-table")).toBeInTheDocument();
    expect(screen.getByText("Técnica de frenada")).toBeInTheDocument();
  });

  it("muestra el botón de nueva sesión", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();
    const link = screen.getByRole("link", { name: /Nueva sesión/i });
    expect(link).toHaveAttribute("href", "/training/sessions/new");
  });

  it("muestra el botón de crear con IA", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();
    const link = screen.getByRole("link", { name: /Crear con IA/i });
    expect(link).toHaveAttribute("href", "/training/sessions/assistant");
  });

  it("muestra la barra de filtros", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();
    expect(screen.getByTestId("filters-bar")).toBeInTheDocument();
  });

  it("muestra la fila de pastillas de vistas hermanas", () => {
    vi.mocked(useTrainingSessions).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useTrainingSessions>);
    renderPage();
    const tabs = screen.getByRole("tablist", { name: /Vistas relacionadas/i });
    expect(tabs).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Calendario" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Sesiones" })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Actividades" })).toBeInTheDocument();
  });

  describe("confirmación de acciones destructivas", () => {
    beforeEach(() => {
      vi.mocked(useTrainingSessions).mockReturnValue({
        isLoading: false,
        isError: false,
        data: [makeSession({ id: 3, status: "planned" })],
      } as unknown as ReturnType<typeof useTrainingSessions>);
    });

    it("abre el modal de ejecutar al pulsar Ejecutar, sin llamar a la mutación todavía", () => {
      const executeMock = { ...mutationStub, mutate: vi.fn() };
      vi.mocked(useExecuteTrainingSession).mockReturnValue(
        executeMock as unknown as ReturnType<typeof useExecuteTrainingSession>,
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Ejecutar-3/i }));
      expect(screen.getByTestId("confirm-dialog")).toBeInTheDocument();
      expect(screen.getByText("Marcar sesión como ejecutada")).toBeInTheDocument();
      expect(executeMock.mutate).not.toHaveBeenCalled();
    });

    it("llama a executeMutation al confirmar el modal de ejecutar", () => {
      const executeMock = { ...mutationStub, mutate: vi.fn() };
      vi.mocked(useExecuteTrainingSession).mockReturnValue(
        executeMock as unknown as ReturnType<typeof useExecuteTrainingSession>,
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Ejecutar-3/i }));
      fireEvent.click(screen.getByRole("button", { name: /confirm-ok/i }));
      expect(executeMock.mutate).toHaveBeenCalledWith(3, expect.any(Object));
    });

    it("cierra el modal de ejecutar al pulsar cancelar sin llamar a la mutación", () => {
      const executeMock = { ...mutationStub, mutate: vi.fn() };
      vi.mocked(useExecuteTrainingSession).mockReturnValue(
        executeMock as unknown as ReturnType<typeof useExecuteTrainingSession>,
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Ejecutar-3/i }));
      fireEvent.click(screen.getByRole("button", { name: /confirm-cancel/i }));
      expect(screen.queryByTestId("confirm-dialog")).toBeNull();
      expect(executeMock.mutate).not.toHaveBeenCalled();
    });

    it("abre el modal de cancelar al pulsar Cancelar, sin llamar a la mutación todavía", () => {
      const cancelMock = { ...mutationStub, mutate: vi.fn() };
      vi.mocked(useCancelTrainingSession).mockReturnValue(
        cancelMock as unknown as ReturnType<typeof useCancelTrainingSession>,
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Cancelar-3/i }));
      expect(screen.getByTestId("confirm-modal")).toBeInTheDocument();
      expect(screen.getByText("Cancelar sesión")).toBeInTheDocument();
      expect(cancelMock.mutate).not.toHaveBeenCalled();
    });

    it("llama a cancelMutation al confirmar el modal de cancelar", () => {
      const cancelMock = { ...mutationStub, mutate: vi.fn() };
      vi.mocked(useCancelTrainingSession).mockReturnValue(
        cancelMock as unknown as ReturnType<typeof useCancelTrainingSession>,
      );
      renderPage();
      fireEvent.click(screen.getByRole("button", { name: /Cancelar-3/i }));
      fireEvent.click(screen.getByRole("button", { name: /confirm-ok/i }));
      expect(cancelMock.mutate).toHaveBeenCalledWith(
        expect.objectContaining({ id: 3, notify: true }),
        expect.any(Object),
      );
    });
  });
});
