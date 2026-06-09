import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { axe, toHaveNoViolations } from "jest-axe";

expect.extend(toHaveNoViolations);

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
  useTrainingSession: vi.fn(() => ({ data: undefined, isLoading: false, isError: false })),
  useSessionAttendance: vi.fn(() => ({ data: [], isLoading: false, isError: false })),
  useCreateTrainingSession: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, isError: false })),
  useUpdateTrainingSession: vi.fn(() => ({ mutateAsync: vi.fn(), isPending: false, isError: false })),
  bulkSetConvocatoria: vi.fn(),
  uploadRouteFile: vi.fn(),
  fetchTrainingSession: vi.fn(),
}));

vi.mock("@/components/training/AthletesMultiSelect", () => ({
  AthletesMultiSelect: ({ onChange }: { onChange: (ids: number[]) => void }) => (
    <button type="button" data-testid="select-athlete" onClick={() => onChange([1])}>
      Seleccionar atleta
    </button>
  ),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel) =>
    sel({ accessToken: "tok", user: { id: 7, role: "coach", club_ids: [1] }, isAuthenticated: true }),
  ),
}));

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return { ...actual, useNavigate: () => vi.fn() };
});

import { SessionFormPage } from "./SessionFormPage";

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

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

describe("SessionFormPage — accesibilidad", () => {
  it("paso General sin violaciones de accesibilidad", async () => {
    const { container } = renderCreate();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });

  it("paso Revisar sin violaciones de accesibilidad", async () => {
    const { container } = renderCreate();
    // Avanzar: General → Atletas → Ruta → Revisar
    fireEvent.change(screen.getByLabelText(/Fecha/i), { target: { value: "2026-12-01" } });
    fireEvent.change(screen.getByLabelText(/Hora de inicio/i), { target: { value: "08:00" } });
    fireEvent.change(screen.getByLabelText(/Lugar/i), { target: { value: "Pista" } });
    fireEvent.change(screen.getByLabelText(/Foco técnico/i), { target: { value: "Técnica" } });
    fireEvent.change(screen.getByLabelText("Descripción"), { target: { value: "Descripción válida" } });
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    fireEvent.click(await screen.findByTestId("select-athlete"));
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    await screen.findByTestId("session-step-route-notes");
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    await screen.findByTestId("session-step-review");

    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
