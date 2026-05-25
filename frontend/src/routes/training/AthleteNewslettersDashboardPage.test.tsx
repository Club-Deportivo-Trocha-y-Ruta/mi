/**
 * Tests para AthleteNewslettersDashboardPage.
 *
 * Cubre: render con MSW data, filter by status, batch generate flow.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    interceptors: { request: { use: vi.fn() }, response: { use: vi.fn() } },
  },
  registerAuthHandlers: vi.fn(),
}));

vi.mock("@/api/athleteNewsletters", () => ({
  useAthleteNewsletters: vi.fn(),
  useBatchCreateNewsletters: vi.fn(),
}));

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "tok",
      user: { role: "coach", first_name: "Juan", last_name: "T", club_ids: [1], id: 10 },
    }),
  ),
}));

import { useAthleteNewsletters, useBatchCreateNewsletters } from "@/api/athleteNewsletters";
import { useAthletes } from "@/hooks/athletes/useAthletes";
import { AthleteNewslettersDashboardPage } from "./AthleteNewslettersDashboardPage";
import type { AthleteOut } from "@/types/athlete.types";
import type { AthleteNewsletter } from "@/types/athleteNewsletter.types";
import { makeNewsletter, makeBatchResult } from "@/test/msw/newsletterHandlers";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeAthlete(overrides?: Partial<AthleteOut>): AthleteOut {
  return {
    id: 42,
    user_id: 100,
    first_name: "Sebastián",
    last_name: "García",
    birth_date: "2012-03-15",
    sex: Sex.M,
    club_join_date: "2024-01-10",
    years_in_club: 2,
    age_decimal: 14.2,
    category: "JUV-M",
    club_id: 1,
    created_at: "2024-01-10T00:00:00Z",
    ...overrides,
  };
}

const mutationStub = {
  mutate: vi.fn(),
  mutateAsync: vi.fn(),
  isPending: false,
  isError: false,
  isSuccess: false,
  data: undefined,
  error: null,
  reset: vi.fn(),
};

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AthleteNewslettersDashboardPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(useBatchCreateNewsletters).mockReturnValue(
    mutationStub as unknown as ReturnType<typeof useBatchCreateNewsletters>,
  );
  vi.mocked(useAthleteNewsletters).mockReturnValue({
    isLoading: false,
    isError: false,
    data: [],
  } as unknown as ReturnType<typeof useAthleteNewsletters>);
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AthleteNewslettersDashboardPage — render básico", () => {
  it("muestra el título de la página", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 0 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();
    expect(screen.getByText(/Boletines Mensuales/i)).toBeInTheDocument();
  });

  it("muestra estado vacío cuando no hay atletas", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 0 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();
    expect(screen.getByTestId("empty-athletes")).toBeInTheDocument();
    expect(screen.getByText(/No hay atletas en el club/i)).toBeInTheDocument();
  });

  it("muestra skeleton durante la carga de atletas", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: true,
      isError: false,
      data: undefined,
    } as unknown as ReturnType<typeof useAthletes>);
    const { container } = renderPage();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("muestra error cuando falla la carga de atletas", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: true,
      data: undefined,
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();
    expect(
      screen.getByText(/No se pudo cargar la lista de atletas/i),
    ).toBeInTheDocument();
  });

  it("muestra la card del atleta cuando hay atletas", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();
    expect(screen.getByTestId("athletes-grid")).toBeInTheDocument();
    expect(
      screen.getByText(/Sebastián García/i),
    ).toBeInTheDocument();
  });
});

describe("AthleteNewslettersDashboardPage — filtro de atletas", () => {
  it("filtra atletas por nombre", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [
          makeAthlete({ id: 1, first_name: "Sebastián", last_name: "García" }),
          makeAthlete({ id: 2, first_name: "Laura", last_name: "Pérez" }),
        ],
        total: 2,
      },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();

    const searchInput = screen.getByPlaceholderText(/Buscar por nombre/i);
    fireEvent.change(searchInput, { target: { value: "Laura" } });

    expect(screen.queryByText(/Sebastián García/i)).not.toBeInTheDocument();
    expect(screen.getByText(/Laura Pérez/i)).toBeInTheDocument();
  });

  it("muestra 'ningún atleta' cuando el filtro no coincide", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        items: [makeAthlete({ first_name: "Sebastián", last_name: "García" })],
        total: 1,
      },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();

    const searchInput = screen.getByPlaceholderText(/Buscar por nombre/i);
    fireEvent.change(searchInput, { target: { value: "XYZ_noexiste" } });

    expect(screen.getByTestId("empty-filtered")).toBeInTheDocument();
  });
});

describe("AthleteNewslettersDashboardPage — batch generate", () => {
  it("abre el modal de batch al presionar el botón", async () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();

    fireEvent.click(screen.getByTestId("open-batch-modal"));
    await waitFor(() => {
      expect(screen.getByTestId("batch-generate-btn")).toBeInTheDocument();
    });
  });

  it("ejecuta batch mutation al confirmar", async () => {
    const mutateMock = vi.fn();
    vi.mocked(useBatchCreateNewsletters).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useBatchCreateNewsletters>);
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();

    fireEvent.click(screen.getByTestId("open-batch-modal"));
    await waitFor(() => screen.getByTestId("batch-generate-btn"));
    fireEvent.click(screen.getByTestId("batch-generate-btn"));

    expect(mutateMock).toHaveBeenCalledWith(
      expect.objectContaining({ year: expect.any(Number), month: expect.any(Number) }),
      expect.any(Object),
    );
  });

  it("muestra el resumen del resultado batch tras éxito", async () => {
    const result = makeBatchResult({ created: 4, skipped: 1 });
    const mutateMock = vi.fn((_payload, opts) => opts?.onSuccess?.(result));
    vi.mocked(useBatchCreateNewsletters).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
      data: result,
      isSuccess: true,
    } as unknown as ReturnType<typeof useBatchCreateNewsletters>);
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();

    // Al abrir el modal con data ya presente en la mutación (mock estático),
    // la UI muestra el bloque de resultado en lugar del botón "Generar".
    fireEvent.click(screen.getByTestId("open-batch-modal"));
    await waitFor(() => {
      expect(screen.getByTestId("batch-result")).toBeInTheDocument();
    });
  });

  it("muestra error cuando batch falla", async () => {
    const axiosError = {
      isAxiosError: true,
      response: { status: 500, data: { detail: "Error del servidor" } },
    };
    const mutateMock = vi.fn((_payload, opts) => opts?.onError?.(axiosError));
    vi.mocked(useBatchCreateNewsletters).mockReturnValue({
      ...mutationStub,
      mutate: mutateMock,
    } as unknown as ReturnType<typeof useBatchCreateNewsletters>);
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();

    fireEvent.click(screen.getByTestId("open-batch-modal"));
    await waitFor(() => screen.getByTestId("batch-generate-btn"));
    fireEvent.click(screen.getByTestId("batch-generate-btn"));

    await waitFor(() => {
      expect(screen.getByRole("alert")).toBeInTheDocument();
    });
  });
});

describe("AthleteNewslettersDashboardPage — selección de periodo", () => {
  it("tiene selectores de mes y año", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 0 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();
    expect(screen.getByLabelText(/Mes/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Año/i)).toBeInTheDocument();
  });

  it("tiene selector de estado de boletín", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [], total: 0 },
    } as unknown as ReturnType<typeof useAthletes>);
    renderPage();
    expect(screen.getByLabelText(/Estado/i)).toBeInTheDocument();
  });
});

describe("AthleteNewslettersDashboardPage — estados de badge por atleta", () => {
  it("muestra badge 'Sin generar' cuando el atleta no tiene newsletter en el periodo", () => {
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    // No hay newsletter para este atleta/periodo
    vi.mocked(useAthleteNewsletters).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [],
    } as unknown as ReturnType<typeof useAthleteNewsletters>);
    renderPage();
    // Buscar el badge en la card del atleta (no en el select de filtro)
    expect(screen.getByTestId("status-badge-42")).toHaveTextContent(/Sin generar/i);
  });

  it("muestra badge 'Borrador' cuando el newsletter está en draft", () => {
    const now = new Date();
    const newsletter: AthleteNewsletter = makeNewsletter({
      athlete_id: 42,
      year: now.getFullYear(),
      month: now.getMonth() + 1,
      status: "draft",
    });
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    vi.mocked(useAthleteNewsletters).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [newsletter],
    } as unknown as ReturnType<typeof useAthleteNewsletters>);
    renderPage();
    expect(screen.getByTestId("status-badge-42")).toHaveTextContent("Borrador");
  });

  it("muestra badge 'Enviado' cuando el newsletter fue enviado", () => {
    const now = new Date();
    const newsletter: AthleteNewsletter = makeNewsletter({
      athlete_id: 42,
      year: now.getFullYear(),
      month: now.getMonth() + 1,
      status: "sent",
      sent_at: "2026-05-01T10:00:00Z",
    });
    vi.mocked(useAthletes).mockReturnValue({
      isLoading: false,
      isError: false,
      data: { items: [makeAthlete()], total: 1 },
    } as unknown as ReturnType<typeof useAthletes>);
    vi.mocked(useAthleteNewsletters).mockReturnValue({
      isLoading: false,
      isError: false,
      data: [newsletter],
    } as unknown as ReturnType<typeof useAthleteNewsletters>);
    renderPage();
    expect(screen.getByTestId("status-badge-42")).toHaveTextContent("Enviado");
  });
});
