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

const DRAFT_KEY = "tyr:session-draft:v1:7:new";

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

describe("Borrador de sesión — autoguardado y restauración", () => {
  it("no muestra el banner de restaurar cuando no hay borrador", () => {
    renderCreate();
    expect(screen.queryByTestId("session-draft-banner")).not.toBeInTheDocument();
  });

  it("ofrece restaurar y repuebla los campos desde un borrador guardado", () => {
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({
        version: "v1",
        step: 1,
        updatedAt: new Date().toISOString(),
        values: {
          scheduled_date: "2027-03-10",
          scheduled_start_time: "07:30",
          duration_min: 90,
          location: "La Buitrera",
          technical_focus: "Curvas",
          description: "Borrador previo",
          session_kind: "salida",
          objectives: "Resistencia",
          route_text: "",
          strava_url: "",
          coach_notes: "",
          convocados_athlete_ids: [1],
        },
      }),
    );

    renderCreate();
    expect(screen.getByTestId("session-draft-banner")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Restaurar/i }));

    expect(screen.getByLabelText(/Lugar/i)).toHaveValue("La Buitrera");
    expect(screen.getByLabelText("Descripción")).toHaveValue("Borrador previo");
    expect(screen.getByRole("radio", { name: "Salida" })).toHaveAttribute("data-state", "on");
    // El banner desaparece tras restaurar.
    expect(screen.queryByTestId("session-draft-banner")).not.toBeInTheDocument();
  });

  it("descartar elimina el borrador de localStorage", () => {
    localStorage.setItem(
      DRAFT_KEY,
      JSON.stringify({ version: "v1", step: 1, updatedAt: "x", values: { location: "X", convocados_athlete_ids: [] } }),
    );
    renderCreate();
    fireEvent.click(screen.getByRole("button", { name: /Descartar/i }));
    expect(localStorage.getItem(DRAFT_KEY)).toBeNull();
    expect(screen.queryByTestId("session-draft-banner")).not.toBeInTheDocument();
  });

  it("autoguarda en localStorage al escribir (debounced)", async () => {
    renderCreate();
    fireEvent.change(screen.getByLabelText(/Lugar/i), {
      target: { value: "Pista nueva" },
    });
    await waitFor(
      () => {
        const raw = localStorage.getItem(DRAFT_KEY);
        expect(raw).toBeTruthy();
        expect(JSON.parse(raw as string).values.location).toBe("Pista nueva");
      },
      { timeout: 2000 },
    );
  });
});
