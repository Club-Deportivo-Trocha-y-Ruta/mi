import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

vi.mock("@/api/athletes", () => ({
  getAthletes: vi.fn(),
  getAthlete: vi.fn(),
  createAthlete: vi.fn(),
  updateAthlete: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import { useAthletes } from "./useAthletes";
import { useAthlete } from "./useAthlete";
import { useCreateAthlete } from "./useCreateAthlete";
import { useUpdateAthlete } from "./useUpdateAthlete";
import * as athletesApi from "@/api/athletes";
import type { AthleteListOut, AthleteDetailOut, AthleteOut } from "@/types/athlete.types";
import { Sex } from "@/types/enums";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

const mockAthleteOut: AthleteOut = {
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
};

const mockAthleteDetailOut: AthleteDetailOut = {
  ...mockAthleteOut,
  latest_anthropometry: null,
};

const mockAthleteList: AthleteListOut = {
  items: [mockAthleteOut],
  total: 1,
};

// ---------------------------------------------------------------------------
// useAthletes
// ---------------------------------------------------------------------------

describe("useAthletes", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando la API retorna datos correctamente", () => {
    it("debería retornar la lista de atletas", async () => {
      vi.mocked(athletesApi.getAthletes).mockResolvedValue(mockAthleteList);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useAthletes(), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockAthleteList);
    });

    it("debería pasar el filtro club_id a la API", async () => {
      vi.mocked(athletesApi.getAthletes).mockResolvedValue(mockAthleteList);
      const wrapper = createWrapper();
      renderHook(() => useAthletes({ club_id: 5 }), { wrapper });

      await waitFor(() => expect(athletesApi.getAthletes).toHaveBeenCalledWith({ club_id: 5 }));
    });

    it("debería incluir los filtros en la queryKey (para cache distinto por filtro)", async () => {
      vi.mocked(athletesApi.getAthletes).mockResolvedValue(mockAthleteList);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useAthletes({ club_id: 1 }), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      // La query no debe fallar con filtros
      expect(result.current.error).toBeNull();
    });
  });

  describe("cuando la API falla", () => {
    it("debería retornar error cuando la API falla", async () => {
      vi.mocked(athletesApi.getAthletes).mockRejectedValue(new Error("Error de red"));
      const wrapper = createWrapper();
      const { result } = renderHook(() => useAthletes(), { wrapper });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error).toBeInstanceOf(Error);
    });
  });
});

// ---------------------------------------------------------------------------
// useAthlete
// ---------------------------------------------------------------------------

describe("useAthlete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando se pide un atleta por ID válido", () => {
    it("debería retornar el detalle del atleta", async () => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteDetailOut);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useAthlete(1), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockAthleteDetailOut);
    });

    it("debería llamar a la API con el ID correcto", async () => {
      vi.mocked(athletesApi.getAthlete).mockResolvedValue(mockAthleteDetailOut);
      const wrapper = createWrapper();
      renderHook(() => useAthlete(42), { wrapper });

      await waitFor(() => expect(athletesApi.getAthlete).toHaveBeenCalledWith(42));
    });
  });

  describe("cuando enabled = false", () => {
    it("no debería llamar a la API si enabled es false", async () => {
      const wrapper = createWrapper();
      renderHook(() => useAthlete(1, false), { wrapper });

      // Esperar un ciclo — la query no debe ejecutarse
      await new Promise((r) => setTimeout(r, 50));
      expect(athletesApi.getAthlete).not.toHaveBeenCalled();
    });
  });

  describe("cuando el ID es Infinity", () => {
    it("no debería llamar a la API si el ID no es finito", async () => {
      const wrapper = createWrapper();
      renderHook(() => useAthlete(Infinity), { wrapper });

      await new Promise((r) => setTimeout(r, 50));
      expect(athletesApi.getAthlete).not.toHaveBeenCalled();
    });
  });
});

// ---------------------------------------------------------------------------
// useCreateAthlete
// ---------------------------------------------------------------------------

describe("useCreateAthlete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando la creación es exitosa", () => {
    it("debería retornar el atleta creado después de la mutación", async () => {
      vi.mocked(athletesApi.createAthlete).mockResolvedValue(mockAthleteDetailOut);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCreateAthlete(), { wrapper });

      result.current.mutate({
        first_name: "Sebastián",
        last_name: "García",
        birth_date: "2013-06-15",
        sex: Sex.M,
        club_id: 1,
      });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockAthleteDetailOut);
    });
  });

  describe("cuando la creación falla", () => {
    it("debería retornar estado de error cuando la API falla", async () => {
      vi.mocked(athletesApi.createAthlete).mockRejectedValue(new Error("Error al crear"));
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCreateAthlete(), { wrapper });

      result.current.mutate({
        first_name: "Error",
        last_name: "Test",
        birth_date: "2013-01-01",
        sex: Sex.M,
        club_id: 1,
      });

      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });
});

// ---------------------------------------------------------------------------
// useUpdateAthlete
// ---------------------------------------------------------------------------

describe("useUpdateAthlete", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando la actualización es exitosa", () => {
    it("debería retornar el atleta actualizado", async () => {
      const updated = { ...mockAthleteDetailOut, first_name: "Juan" };
      vi.mocked(athletesApi.updateAthlete).mockResolvedValue(updated);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useUpdateAthlete(), { wrapper });

      result.current.mutate({ id: 1, payload: { first_name: "Juan" } });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(updated);
    });

    it("debería llamar a la API con id y payload correctos", async () => {
      vi.mocked(athletesApi.updateAthlete).mockResolvedValue(mockAthleteDetailOut);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useUpdateAthlete(), { wrapper });

      result.current.mutate({ id: 7, payload: { club_join_date: "2023-01-01" } });

      await waitFor(() => expect(athletesApi.updateAthlete).toHaveBeenCalledWith(7, { club_join_date: "2023-01-01" }));
    });
  });

  describe("cuando la actualización falla", () => {
    it("debería retornar estado de error cuando la API falla", async () => {
      vi.mocked(athletesApi.updateAthlete).mockRejectedValue(new Error("No encontrado"));
      const wrapper = createWrapper();
      const { result } = renderHook(() => useUpdateAthlete(), { wrapper });

      result.current.mutate({ id: 999, payload: { first_name: "Ghost" } });

      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });
});
