import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — todos antes de importar componentes (feature 032, US3)
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
      user: { role: "coach", id: 10, first_name: "Juan", last_name: "Test" },
      isAuthenticated: true,
    }),
  ),
}));

vi.mock("@/api/trainingSessions", () => ({
  useTrainingSessions: vi.fn(),
  useExecuteTrainingSession: vi.fn(),
  useCancelTrainingSession: vi.fn(),
}));

import {
  useTrainingSessions,
  useExecuteTrainingSession,
  useCancelTrainingSession,
} from "@/api/trainingSessions";
import type { SessionFilters, TrainingSession } from "@/types/trainingSession.types";
import { useTrainingFiltersStore } from "@/store/trainingFiltersStore";
import { SessionFiltersBar } from "@/components/training/SessionFiltersBar";
import { SessionsListPage } from "@/routes/training/SessionsListPage";

// Fecha "hoy" fija para todo el archivo: 2026-06-15T15:00:00Z = 10:00 en
// America/Bogota (UTC-5) — deterministica, no wall-clock (T039).
const MOCKED_NOW = new Date("2026-06-15T15:00:00Z");
const TODAY_ISO = "2026-06-15";

function makeSession(overrides?: Partial<TrainingSession>): TrainingSession {
  return {
    id: 1,
    club_id: 1,
    created_by_user_id: 10,
    status: "planned",
    scheduled_date: TODAY_ISO,
    scheduled_start_time: "08:00:00",
    duration_min: 90,
    location: "Pista XCO",
    technical_focus: "Técnica de frenada",
    description: "Sesión de técnica",
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
    ...overrides,
  };
}

const mutationStub = {
  mutate: vi.fn(),
  isPending: false,
  mutateAsync: vi.fn(),
  reset: vi.fn(),
  isIdle: true,
  isSuccess: false,
  isError: false,
  data: undefined,
  error: null,
  variables: undefined,
  context: undefined,
  status: "idle",
  failureCount: 0,
  failureReason: null,
  submittedAt: 0,
};

function renderFiltersBarOnly() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <SessionFiltersBar />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

function renderListPage() {
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
  vi.useFakeTimers();
  vi.setSystemTime(MOCKED_NOW);
  // Estado base: filtro de mes actual (no "hoy"), como el store real por
  // defecto — la prueba solo debe atribuir el efecto a pulsar "Hoy".
  useTrainingFiltersStore.setState({ from_date: "2026-06-01", to_date: "2026-06-30", status: "" });
  vi.mocked(useExecuteTrainingSession).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useExecuteTrainingSession>,
  );
  vi.mocked(useCancelTrainingSession).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useCancelTrainingSession>,
  );
});

afterEach(() => {
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("SessionFiltersBar — atajo 'Hoy' (feature 032, US3)", () => {
  it("clic en 'Hoy' fija from_date y to_date del store a la fecha de hoy mockeada", () => {
    renderFiltersBarOnly();

    fireEvent.click(screen.getByRole("button", { name: "Hoy" }));

    const state = useTrainingFiltersStore.getState();
    expect(state.from_date).toBe(TODAY_ISO);
    expect(state.to_date).toBe(TODAY_ISO);
  });

  it("con una sesión sembrada hoy, la lista muestra exactamente esa sesión", () => {
    const todaySession = makeSession({ id: 5, technical_focus: "Sesión sembrada hoy" });

    vi.mocked(useTrainingSessions).mockImplementation((filters?: SessionFilters) => {
      const isTodayQuery = filters?.from_date === TODAY_ISO && filters?.to_date === TODAY_ISO;
      return {
        data: isTodayQuery ? [todaySession] : [],
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof useTrainingSessions>;
    });

    renderListPage();
    fireEvent.click(screen.getByRole("button", { name: "Hoy" }));

    // SessionsTable renderiza card móvil + fila desktop simultáneamente
    // (una oculta por CSS) — se espera el texto duplicado en el DOM.
    expect(screen.getAllByText("Sesión sembrada hoy").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText(/No hay sesión hoy/i)).not.toBeInTheDocument();
  });

  it("sin sesión hoy, muestra el fallback con la próxima sesión (orden ascendente) y la etiqueta esperada", () => {
    // API en orden DESC (furthest-future-first, el gotcha R6/R10): el
    // componente debe reordenar ascendente antes de tomar el primero.
    const laterSession = makeSession({
      id: 8,
      scheduled_date: "2026-06-20",
      scheduled_start_time: "07:00:00",
      technical_focus: "Sesión más lejana",
    });
    const nextSession = makeSession({
      id: 7,
      scheduled_date: "2026-06-17",
      scheduled_start_time: "09:00:00",
      technical_focus: "Próxima sesión más cercana",
    });

    vi.mocked(useTrainingSessions).mockImplementation((filters?: SessionFilters) => {
      const isTodayQuery = filters?.from_date === TODAY_ISO && filters?.to_date === TODAY_ISO;
      if (isTodayQuery) {
        return {
          data: [],
          isLoading: false,
          isError: false,
          refetch: vi.fn(),
        } as unknown as ReturnType<typeof useTrainingSessions>;
      }
      return {
        data: [laterSession, nextSession],
        isLoading: false,
        isError: false,
        refetch: vi.fn(),
      } as unknown as ReturnType<typeof useTrainingSessions>;
    });

    renderListPage();
    fireEvent.click(screen.getByRole("button", { name: "Hoy" }));

    expect(screen.getByText(/No hay sesión hoy — próxima sesión:/i)).toBeInTheDocument();
    expect(screen.getAllByText("Próxima sesión más cercana").length).toBeGreaterThanOrEqual(1);
    expect(screen.queryByText("Sesión más lejana")).not.toBeInTheDocument();
  });
});
