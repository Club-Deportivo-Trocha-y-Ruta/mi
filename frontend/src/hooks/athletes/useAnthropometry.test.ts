import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

// ---------------------------------------------------------------------------
// Mocks declarados antes de importar los hooks
// ---------------------------------------------------------------------------

vi.mock("@/api/athletes", () => ({
  getAnthropometry: vi.fn(),
  createAnthropometry: vi.fn(),
}));

import { useAnthropometry, useCreateAnthropometry } from "./useAnthropometry";
import * as athletesApi from "@/api/athletes";
import type { AnthropometricRecord } from "@/types/anthropometry.types";
import { MaturationStatus } from "@/types/enums";

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

const mockRecord: AnthropometricRecord = {
  id: 1,
  athlete_id: 1,
  evaluation_date: "2026-01-15",
  mesocycle: 1,
  weight_kg: 45.0,
  standing_height_cm: 155.0,
  arm_span_cm: null,
  sitting_height_cm: 73.0,
  leg_length_cm: 82.0,
  leg_sitting_ratio: 1.1233,
  maturity_offset: -0.5,
  age_at_phv: 13.5,
  maturation_status: MaturationStatus.CircaPHV,
  training_implications: null,
  evaluated_by: 1,
  created_at: "2026-01-15T00:00:00Z",
  notes: null,
};

const mockCreate = {
  evaluation_date: "2026-01-15",
  weight_kg: 45.0,
  standing_height_cm: 155.0,
  sitting_height_cm: 73.0,
};

// ---------------------------------------------------------------------------
// useAnthropometry
// ---------------------------------------------------------------------------

describe("useAnthropometry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando la API retorna registros", () => {
    it("debería retornar la lista de registros antropométricos", async () => {
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([mockRecord]);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useAnthropometry(1), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual([mockRecord]);
    });

    it("debería llamar a la API con el athleteId correcto", async () => {
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([mockRecord]);
      const wrapper = createWrapper();
      renderHook(() => useAnthropometry(42), { wrapper });

      await waitFor(() =>
        expect(athletesApi.getAnthropometry).toHaveBeenCalledWith(42),
      );
    });

    it("debería retornar lista vacía si no hay registros", async () => {
      vi.mocked(athletesApi.getAnthropometry).mockResolvedValue([]);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useAnthropometry(1), { wrapper });

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual([]);
    });
  });

  describe("cuando athleteId no es válido (≤ 0)", () => {
    it("no debería ejecutar la query si athleteId es 0", async () => {
      const wrapper = createWrapper();
      renderHook(() => useAnthropometry(0), { wrapper });

      await new Promise((r) => setTimeout(r, 50));
      expect(athletesApi.getAnthropometry).not.toHaveBeenCalled();
    });

    it("no debería ejecutar la query si athleteId es negativo", async () => {
      const wrapper = createWrapper();
      renderHook(() => useAnthropometry(-1), { wrapper });

      await new Promise((r) => setTimeout(r, 50));
      expect(athletesApi.getAnthropometry).not.toHaveBeenCalled();
    });
  });

  describe("cuando la API falla", () => {
    it("debería poner isError = true cuando la API lanza error", async () => {
      vi.mocked(athletesApi.getAnthropometry).mockRejectedValue(
        new Error("Error de red"),
      );
      const wrapper = createWrapper();
      const { result } = renderHook(() => useAnthropometry(1), { wrapper });

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(result.current.error).toBeInstanceOf(Error);
    });
  });
});

// ---------------------------------------------------------------------------
// useCreateAnthropometry
// ---------------------------------------------------------------------------

describe("useCreateAnthropometry", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("cuando la creación es exitosa", () => {
    it("debería retornar el registro creado tras la mutación", async () => {
      vi.mocked(athletesApi.createAnthropometry).mockResolvedValue(mockRecord);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCreateAnthropometry(1), {
        wrapper,
      });

      result.current.mutate(mockCreate);

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockRecord);
    });

    it("debería llamar a la API con athleteId y payload correctos", async () => {
      vi.mocked(athletesApi.createAnthropometry).mockResolvedValue(mockRecord);
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCreateAnthropometry(5), {
        wrapper,
      });

      result.current.mutate(mockCreate);

      await waitFor(() =>
        expect(athletesApi.createAnthropometry).toHaveBeenCalledWith(
          5,
          mockCreate,
        ),
      );
    });

    it("invalida el caché de explicación PHV (`['ai','phv',athleteId]`) tras éxito", async () => {
      // Una nueva medición cambia el `anthropometric_record_id` más reciente,
      // así que el caché backend queda invalidado implícitamente. El frontend
      // debe refetch para que el GET devuelva 204 y el card vuelva a idle.
      vi.mocked(athletesApi.createAnthropometry).mockResolvedValue(mockRecord);
      const queryClient = new QueryClient({
        defaultOptions: {
          queries: { retry: false },
          mutations: { retry: false },
        },
      });
      const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

      const wrapper = ({ children }: { children: React.ReactNode }) =>
        createElement(QueryClientProvider, { client: queryClient }, children);
      const { result } = renderHook(() => useCreateAnthropometry(7), {
        wrapper,
      });

      result.current.mutate(mockCreate);
      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(invalidateSpy).toHaveBeenCalledWith({
        queryKey: ["ai", "phv", 7],
      });
    });
  });

  describe("cuando la creación falla", () => {
    it("debería poner isError = true cuando la API falla", async () => {
      vi.mocked(athletesApi.createAnthropometry).mockRejectedValue(
        new Error("Error al guardar"),
      );
      const wrapper = createWrapper();
      const { result } = renderHook(() => useCreateAnthropometry(1), {
        wrapper,
      });

      result.current.mutate(mockCreate);

      await waitFor(() => expect(result.current.isError).toBe(true));
    });
  });
});
