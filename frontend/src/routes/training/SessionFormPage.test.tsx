import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSession: vi.fn(),
  useSessionAttendance: vi.fn(),
  useCreateTrainingSession: vi.fn(),
  useUpdateTrainingSession: vi.fn(),
  bulkSetConvocatoria: vi.fn(),
  uploadRouteFile: vi.fn(),
  fetchTrainingSession: vi.fn(),
}));

vi.mock("@/components/training/AthletesMultiSelect", () => ({
  AthletesMultiSelect: ({
    onChange,
    error,
  }: {
    value: number[];
    onChange: (ids: number[]) => void;
    error?: string;
  }) => (
    <div>
      <button
        type="button"
        data-testid="select-athlete"
        onClick={() => onChange([1])}
      >
        Seleccionar atleta
      </button>
      {error && <span data-testid="convocados-error">{error}</span>}
    </div>
  ),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) =>
    sel({
      accessToken: "tok",
      user: { id: 7, role: "coach", first_name: "Juan", last_name: "Test", club_ids: [1] },
      isAuthenticated: true,
    }),
  ),
}));

import {
  useTrainingSession,
  useSessionAttendance,
  useCreateTrainingSession,
  useUpdateTrainingSession,
} from "@/api/trainingSessions";
import { SessionFormPage } from "./SessionFormPage";

const mockNavigate = vi.fn();
vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => mockNavigate,
  };
});

function renderCreate() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={["/training/sessions/new"]}>
        <Routes>
          <Route path="/training/sessions/new" element={<SessionFormPage mode="create" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

const mutateAsyncStub = vi.fn();

/** Llena el paso 1 (General) con datos válidos. */
function fillStep1() {
  fireEvent.change(screen.getByLabelText(/Fecha/i), { target: { value: "2026-12-01" } });
  fireEvent.change(screen.getByLabelText(/Hora de inicio/i), { target: { value: "08:00" } });
  fireEvent.change(screen.getByLabelText(/Lugar/i), { target: { value: "Pista XCO" } });
  fireEvent.change(screen.getByLabelText(/Foco técnico/i), {
    target: { value: "Técnica de frenada" },
  });
  fireEvent.change(screen.getByLabelText("Descripción"), {
    target: { value: "Descripción completa de la sesión" },
  });
}

async function advance() {
  fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  vi.mocked(useTrainingSession).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useTrainingSession>);
  vi.mocked(useSessionAttendance).mockReturnValue({
    data: [],
    isLoading: false,
    isError: false,
  } as unknown as ReturnType<typeof useSessionAttendance>);
  vi.mocked(useCreateTrainingSession).mockReturnValue({
    mutateAsync: mutateAsyncStub,
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useCreateTrainingSession>);
  vi.mocked(useUpdateTrainingSession).mockReturnValue({
    mutateAsync: vi.fn(),
    isPending: false,
    isError: false,
  } as unknown as ReturnType<typeof useUpdateTrainingSession>);
});

describe("SessionFormPage — asistente (modo crear)", () => {
  it("renderiza el paso General con los campos requeridos y el stepper", () => {
    renderCreate();
    expect(screen.getByText("Nueva sesión")).toBeInTheDocument();
    expect(screen.getByRole("list", { name: /Pasos para crear la sesión/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Hora de inicio/i)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /Duración/i })).toBeInTheDocument();
    expect(screen.getByLabelText(/Lugar/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Foco técnico/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Descripción")).toBeInTheDocument();
    expect(screen.getByLabelText(/Objetivos de la sesión/i)).toBeInTheDocument();
  });

  it("no expone el selector de tipo de sesión: el módulo es solo entrenamientos", () => {
    renderCreate();
    expect(screen.queryByTestId("session-kind-toggle")).not.toBeInTheDocument();
    expect(screen.queryByRole("radio", { name: "Salida" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("radio", { name: "Actividad conjunta" }),
    ).not.toBeInTheDocument();
  });

  it("bloquea 'Siguiente' y muestra resumen de errores si el paso es inválido", async () => {
    renderCreate();
    await advance();
    expect(await screen.findByTestId("session-error-summary")).toBeInTheDocument();
    // El mensaje aparece tanto inline como en el resumen.
    expect(screen.getAllByText(/La fecha es requerida/i).length).toBeGreaterThan(0);
    // No avanzó: seguimos en el paso General.
    expect(screen.getByTestId("session-step-general")).toBeInTheDocument();
  });

  it("avanza al paso de atletas cuando el paso General es válido", async () => {
    renderCreate();
    fillStep1();
    await advance();
    expect(await screen.findByTestId("session-step-athletes")).toBeInTheDocument();
  });

  it("flujo completo: crea la sesión con send_notification segun el check de revisión", async () => {
    mutateAsyncStub.mockResolvedValueOnce({ id: 99 });
    renderCreate();

    // Paso 1
    fillStep1();
    fireEvent.click(screen.getByRole("button", { name: "2 h 30 min" }));
    await advance();

    // Paso 2 — atletas
    fireEvent.click(await screen.findByTestId("select-athlete"));
    await advance();

    // Paso 3 — ruta y notas (todo opcional)
    await screen.findByTestId("session-step-route-notes");
    await advance();

    // Paso 4 — revisión: marcar notificar y enviar
    const review = await screen.findByTestId("session-step-review");
    expect(review).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("notify-parents-checkbox"));
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    await waitFor(() => {
      expect(mutateAsyncStub).toHaveBeenCalledWith(
        expect.objectContaining({
          scheduled_date: "2026-12-01",
          duration_min: 150,
          location: "Pista XCO",
          technical_focus: "Técnica de frenada",
          convocados_athlete_ids: [1],
          send_notification: true,
        }),
      );
    });

    // Redirige directo al detalle de la sesión creada, sin pantalla intermedia.
    await waitFor(() => {
      expect(mockNavigate).toHaveBeenCalledWith("/training/sessions/99");
    });
  });

  it("crea con send_notification=false cuando no se marca el check", async () => {
    mutateAsyncStub.mockResolvedValueOnce({ id: 88 });
    renderCreate();

    fillStep1();
    await advance();
    fireEvent.click(await screen.findByTestId("select-athlete"));
    await advance();
    await screen.findByTestId("session-step-route-notes");
    await advance();
    await screen.findByTestId("session-step-review");
    fireEvent.click(screen.getByTestId("session-wizard-submit"));

    await waitFor(() => {
      expect(mutateAsyncStub).toHaveBeenCalledWith(
        expect.objectContaining({ duration_min: 60, send_notification: false }),
      );
    });
  });
});
