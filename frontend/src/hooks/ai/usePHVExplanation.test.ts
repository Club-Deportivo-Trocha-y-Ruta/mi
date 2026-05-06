import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import { AxiosError, AxiosHeaders } from "axios";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/ai", async () => {
  const actual = await vi.importActual<typeof import("@/api/ai")>("@/api/ai");
  return {
    ...actual,
    getPHVExplanation: vi.fn(),
    getPHVExplanationCached: vi.fn(),
  };
});

import * as aiApi from "@/api/ai";
import { MaturationStatus } from "@/types/enums";
import type { PHVExplanationResponse } from "@/types/ai.types";

import {
  usePHVExplanation,
  usePHVExplanationCached,
} from "./usePHVExplanation";

function createWrapper() {
  // Para tests de retry con backoff, mantenemos retries pero sin delay.
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

const mockResponse: PHVExplanationResponse = {
  text: "Su hijo está en Pre-PHV. Priorizamos juego y técnica.",
  model: "fake-model",
  provider: "fake",
  generated_at: "2026-05-05T10:00:00Z",
  age_group: "10-12",
  maturation_status: MaturationStatus.PrePHV,
};

function axiosErrorWith(status: number): AxiosError {
  return new AxiosError(
    `Request failed with status code ${status}`,
    String(status),
    undefined,
    undefined,
    {
      data: { detail: "x" },
      status,
      statusText: "",
      headers: {},
      config: { headers: new AxiosHeaders() },
    },
  );
}

describe("usePHVExplanation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe("camino feliz", () => {
    it("retorna la explicación tras la mutación", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockResolvedValue(mockResponse);
      const wrapper = createWrapper();
      const { result } = renderHook(() => usePHVExplanation(42), { wrapper });

      result.current.mutate();

      await waitFor(() => expect(result.current.isSuccess).toBe(true));
      expect(result.current.data).toEqual(mockResponse);
      expect(aiApi.getPHVExplanation).toHaveBeenCalledWith(42, {
        signal: undefined,
      });
    });

    it("permite cancelar via AbortSignal", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockResolvedValue(mockResponse);
      const wrapper = createWrapper();
      const { result } = renderHook(() => usePHVExplanation(42), { wrapper });

      const controller = new AbortController();
      result.current.mutate({ signal: controller.signal });

      await waitFor(() =>
        expect(aiApi.getPHVExplanation).toHaveBeenCalledWith(42, {
          signal: controller.signal,
        }),
      );
    });
  });

  describe("manejo de errores", () => {
    it("expone el error sin reintentar 422 (no records)", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockRejectedValue(
        axiosErrorWith(422),
      );
      const wrapper = createWrapper();
      const { result } = renderHook(() => usePHVExplanation(1), { wrapper });

      result.current.mutate();

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(aiApi.getPHVExplanation).toHaveBeenCalledTimes(1);
    });

    it("no reintenta 502 (guardrail)", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockRejectedValue(
        axiosErrorWith(502),
      );
      const wrapper = createWrapper();
      const { result } = renderHook(() => usePHVExplanation(1), { wrapper });

      result.current.mutate();

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(aiApi.getPHVExplanation).toHaveBeenCalledTimes(1);
    });

    it("no reintenta 403 (forbidden)", async () => {
      vi.mocked(aiApi.getPHVExplanation).mockRejectedValue(
        axiosErrorWith(403),
      );
      const wrapper = createWrapper();
      const { result } = renderHook(() => usePHVExplanation(1), { wrapper });

      result.current.mutate();

      await waitFor(() => expect(result.current.isError).toBe(true));
      expect(aiApi.getPHVExplanation).toHaveBeenCalledTimes(1);
    });
  });
});


// ---------------------------------------------------------------------------
// usePHVExplanationCached — query GET de la caché backend
// ---------------------------------------------------------------------------

describe("usePHVExplanationCached", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("retorna el contenido cacheado cuando el backend responde 200", async () => {
    vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(mockResponse);
    const wrapper = createWrapper();
    const { result } = renderHook(() => usePHVExplanationCached(42, true), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toEqual(mockResponse);
    expect(aiApi.getPHVExplanationCached).toHaveBeenCalledWith(42);
  });

  it("retorna null cuando el backend responde 204 (cache miss)", async () => {
    vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(null);
    const wrapper = createWrapper();
    const { result } = renderHook(() => usePHVExplanationCached(42, true), {
      wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
  });

  it("no ejecuta la query si hasRecords=false", async () => {
    const wrapper = createWrapper();
    renderHook(() => usePHVExplanationCached(42, false), { wrapper });

    await new Promise((r) => setTimeout(r, 50));
    expect(aiApi.getPHVExplanationCached).not.toHaveBeenCalled();
  });

  it("no ejecuta la query si athleteId <= 0", async () => {
    const wrapper = createWrapper();
    renderHook(() => usePHVExplanationCached(0, true), { wrapper });

    await new Promise((r) => setTimeout(r, 50));
    expect(aiApi.getPHVExplanationCached).not.toHaveBeenCalled();
  });
});

// ---------------------------------------------------------------------------
// Sincronización: mutation.onSuccess actualiza el query del caché
// ---------------------------------------------------------------------------

describe("usePHVExplanation + usePHVExplanationCached integración", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("tras una mutación exitosa, el query del caché refleja el nuevo dato sin GET extra", async () => {
    // Cache inicial vacío.
    vi.mocked(aiApi.getPHVExplanationCached).mockResolvedValue(null);
    vi.mocked(aiApi.getPHVExplanation).mockResolvedValue(mockResponse);

    // Compartimos el mismo QueryClient entre los dos hooks (como en el card).
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    });
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(
      () => ({
        cached: usePHVExplanationCached(42, true),
        mutation: usePHVExplanation(42),
      }),
      { wrapper },
    );

    // Espera a que el query inicial resuelva con null.
    await waitFor(() => expect(result.current.cached.isSuccess).toBe(true));
    expect(result.current.cached.data).toBeNull();

    // Dispara la mutación (Generar).
    result.current.mutation.mutate();
    await waitFor(() => expect(result.current.mutation.isSuccess).toBe(true));

    // El query del caché ahora refleja el resultado de la mutación
    // (gracias a setQueryData en onSuccess) sin haber llamado GET de nuevo.
    expect(result.current.cached.data).toEqual(mockResponse);
    expect(aiApi.getPHVExplanationCached).toHaveBeenCalledTimes(1);
  });
});
