import { describe, it, expect, vi, beforeEach } from "vitest";
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { axe } from "jest-axe";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// ---------------------------------------------------------------------------
// Mocks — deben declararse antes de los imports de producción
// ---------------------------------------------------------------------------

vi.mock("@/api/athletes", () => ({
  getAthlete: vi.fn().mockResolvedValue({
    id: 1,
    user_id: 10,
    first_name: "Sebastián",
    last_name: "García",
    birth_date: "2013-06-15",
    sex: "M",
    club_join_date: "2024-01-01",
    years_in_club: 2.3,
    age_decimal: 12.8,
    category: "Pre-juvenil A",
    club_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    latest_anthropometry: null,
  }),
}));

vi.mock("@/hooks/athletes/useAthletes", () => ({
  useAthletes: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn(),
}));

// AthletesTable ya tiene su propia suite dedicada (AthletesTable.test.tsx);
// aquí solo verificamos que AthletesListPage le pasa las filas correctas.
vi.mock("@/components/athletes/AthletesTable", () => ({
  AthletesTable: ({
    items,
  }: {
    items: { id: number; first_name: string; last_name: string }[];
  }) => (
    <div data-testid="athletes-table">
      {items.map((athlete) => (
        <div key={athlete.id}>
          {athlete.first_name} {athlete.last_name}
        </div>
      ))}
    </div>
  ),
}));

import { useAthletes } from "@/hooks/athletes/useAthletes";
import { useAuthStore } from "@/store/auth.store";
import { Sex } from "@/types/enums";
import type { AthleteListOut, AthleteOut } from "@/types/athlete.types";
import { AthletesListPage } from "./AthletesListPage";

// ---------------------------------------------------------------------------
// Fixtures y helpers
// ---------------------------------------------------------------------------

function makeAthlete(overrides?: Partial<AthleteOut>): AthleteOut {
  return {
    id: 1,
    user_id: 10,
    first_name: "Sebastián",
    last_name: "García",
    birth_date: "2013-06-15",
    sex: Sex.M,
    club_join_date: "2024-01-01",
    years_in_club: 2.3,
    age_decimal: 12.8,
    category: "Pre-juvenil A",
    club_id: 1,
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

function mockAuthAs(role: "admin" | "coach" | "parent") {
  const state = {
    accessToken: "test-token",
    user: { id: 1, role, first_name: "User", last_name: "Test" },
    isAuthenticated: true,
  };
  vi.mocked(useAuthStore).mockImplementation(
    ((sel: (s: typeof state) => unknown) => sel(state)) as unknown as typeof useAuthStore,
  );
}

function mockAthletesQuery(
  overrides: Partial<ReturnType<typeof useAthletes>>,
): void {
  vi.mocked(useAthletes).mockReturnValue({
    isLoading: false,
    isError: false,
    data: undefined,
    refetch: vi.fn(),
    ...overrides,
  } as unknown as ReturnType<typeof useAthletes>);
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter>
        <AthletesListPage />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  mockAuthAs("coach");
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("AthletesListPage", () => {
  it("muestra skeleton durante la carga", () => {
    mockAthletesQuery({ isLoading: true, data: undefined });
    const { container } = renderPage();
    expect(container.querySelector(".animate-pulse")).toBeInTheDocument();
  });

  it("muestra error cuando falla la carga", () => {
    mockAthletesQuery({ isError: true, data: undefined });
    renderPage();
    expect(
      screen.getByText(/No se pudo cargar la lista de atletas/i),
    ).toBeInTheDocument();
  });

  it("reintenta la consulta de atletas al pulsar 'Reintentar'", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    mockAthletesQuery({ isError: true, data: undefined, refetch });
    renderPage();

    const retryButton = screen.getByRole("button", { name: /Reintentar/i });
    await user.click(retryButton);

    expect(refetch).toHaveBeenCalledTimes(1);
  });

  it("no muestra el botón 'Reintentar' cuando no hay error", () => {
    mockAthletesQuery({ data: { items: [], total: 0 } as AthleteListOut });
    renderPage();
    expect(
      screen.queryByRole("button", { name: /Reintentar/i }),
    ).not.toBeInTheDocument();
  });

  it("muestra estado vacío cuando no hay atletas", () => {
    mockAthletesQuery({ data: { items: [], total: 0 } as AthleteListOut });
    renderPage();
    expect(
      screen.getByText(/No hay atletas registrados/i),
    ).toBeInTheDocument();
  });

  it("muestra la tabla con atletas cuando hay datos", async () => {
    mockAthletesQuery({
      data: { items: [makeAthlete()], total: 1 } as AthleteListOut,
    });
    renderPage();
    expect(await screen.findByTestId("athletes-table")).toBeInTheDocument();
    expect(screen.getByText("Sebastián García")).toBeInTheDocument();
  });

  it("muestra el encabezado y el botón de agregar atleta para coach", () => {
    mockAthletesQuery({
      data: { items: [makeAthlete()], total: 1 } as AthleteListOut,
    });
    renderPage();
    expect(screen.getByRole("heading", { name: "Atletas" })).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Agregar atleta/i }),
    ).toHaveAttribute("href", "/athletes/new");
  });

  it("oculta el botón de agregar atleta para roles distintos de coach", () => {
    mockAuthAs("parent");
    mockAthletesQuery({
      data: { items: [makeAthlete()], total: 1 } as AthleteListOut,
    });
    renderPage();
    expect(
      screen.queryByRole("link", { name: /Agregar atleta/i }),
    ).not.toBeInTheDocument();
  });

  describe("accesibilidad", () => {
    it("0 violaciones jest-axe con atletas cargados", async () => {
      mockAthletesQuery({
        data: { items: [makeAthlete()], total: 1 } as AthleteListOut,
      });
      const { container } = renderPage();
      await screen.findByTestId("athletes-table");
      // Flush la promesa de getAthlete (detailQueries) para no dejar un
      // update de estado pendiente fuera de act() antes de correr axe.
      await act(async () => {
        await Promise.resolve();
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("0 violaciones jest-axe en estado de error", async () => {
      mockAthletesQuery({ isError: true, data: undefined });
      const { container } = renderPage();
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it("0 violaciones jest-axe en estado vacío", async () => {
      mockAthletesQuery({ data: { items: [], total: 0 } as AthleteListOut });
      const { container } = renderPage();
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
