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
  useCreateTrainingSession: vi.fn(),
  useUpdateTrainingSession: vi.fn(),
}));

vi.mock("@/components/training/AthletesMultiSelect", () => ({
  AthletesMultiSelect: ({
    onChange,
    error,
  }: {
    ageGroup: string;
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
      user: { role: "coach", first_name: "Juan", last_name: "Test", club_ids: [1] },
      isAuthenticated: true,
    }),
  ),
}));

import {
  useTrainingSession,
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

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useTrainingSession).mockReturnValue({
    data: undefined,
    isLoading: false,
    isError: false,
  } as ReturnType<typeof useTrainingSession>);
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

describe("SessionFormPage — modo crear", () => {
  it("renderiza el formulario con los campos requeridos", () => {
    renderCreate();
    expect(screen.getByText("Nueva sesión")).toBeInTheDocument();
    expect(screen.getByLabelText(/Fecha/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Hora de inicio/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Duración/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Lugar/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Foco técnico/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Descripción/i)).toBeInTheDocument();
  });

  it("muestra errores de validación al hacer submit sin datos", async () => {
    renderCreate();
    const submitBtn = screen.getByRole("button", { name: /Crear sesión/i });
    fireEvent.click(submitBtn);
    await waitFor(() => {
      expect(screen.getByText(/La fecha es requerida/i)).toBeInTheDocument();
    });
  });

  it("rechaza fecha en el pasado", async () => {
    renderCreate();
    const dateInput = screen.getByLabelText(/Fecha/i);
    fireEvent.change(dateInput, { target: { value: "2020-01-01" } });
    const submitBtn = screen.getByRole("button", { name: /Crear sesión/i });
    fireEvent.click(submitBtn);
    await waitFor(() => {
      expect(screen.getByText(/no puede ser en el pasado/i)).toBeInTheDocument();
    });
  });

  it("muestra error cuando no hay atletas convocados", async () => {
    renderCreate();
    const dateInput = screen.getByLabelText(/Fecha/i);
    fireEvent.change(dateInput, { target: { value: "2026-12-01" } });
    const timeInput = screen.getByLabelText(/Hora de inicio/i);
    fireEvent.change(timeInput, { target: { value: "08:00" } });
    const locationInput = screen.getByLabelText(/Lugar/i);
    fireEvent.change(locationInput, { target: { value: "Pista XCO" } });
    const focusInput = screen.getByLabelText(/Foco técnico/i);
    fireEvent.change(focusInput, { target: { value: "Técnica" } });
    const descInput = screen.getByLabelText(/Descripción/i);
    fireEvent.change(descInput, { target: { value: "Descripción de prueba" } });
    const submitBtn = screen.getByRole("button", { name: /Crear sesión/i });
    fireEvent.click(submitBtn);
    await waitFor(() => {
      expect(screen.getByTestId("convocados-error")).toBeInTheDocument();
    });
  });

  it("llama a createMutation con el payload correcto al submit válido", async () => {
    mutateAsyncStub.mockResolvedValueOnce({ id: 99 });
    renderCreate();

    fireEvent.change(screen.getByLabelText(/Fecha/i), { target: { value: "2026-12-01" } });
    fireEvent.change(screen.getByLabelText(/Hora de inicio/i), { target: { value: "08:00" } });
    fireEvent.change(screen.getByLabelText(/Lugar/i), { target: { value: "Pista XCO" } });
    fireEvent.change(screen.getByLabelText(/Foco técnico/i), { target: { value: "Técnica de frenada" } });
    fireEvent.change(screen.getByLabelText(/Descripción/i), { target: { value: "Descripción completa para la sesión" } });
    fireEvent.click(screen.getByTestId("select-athlete"));

    fireEvent.click(screen.getByRole("button", { name: /Crear sesión/i }));

    await waitFor(() => {
      expect(mutateAsyncStub).toHaveBeenCalledWith(
        expect.objectContaining({
          scheduled_date: "2026-12-01",
          location: "Pista XCO",
          technical_focus: "Técnica de frenada",
          convocados_athlete_ids: [1],
        }),
      );
    });
    expect(mockNavigate).toHaveBeenCalledWith("/training/sessions/99");
  });
});
