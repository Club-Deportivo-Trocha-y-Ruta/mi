/**
 * Tests de useAthleteRaceHistory (feature 045, T035).
 *
 * Cubre el parámetro `seriesKind`:
 *  - por defecto (`"cup"`) NO envía `series_kind` — los llamadores previos
 *    (`HistoryProgressionCard`) piden exactamente lo mismo que antes;
 *  - `"all"` y `"championship"` sí lo envían;
 *  - cada variante tiene su propia clave de caché, bajo el prefijo
 *    `["athlete-race-history", id]` (invalidar por atleta las alcanza todas).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn() },
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (sel: (s: { accessToken: string }) => unknown) =>
    sel({ accessToken: "test-token" }),
}));

import * as clientModule from "@/api/client";
import { useAthleteRaceHistory } from "@/hooks/race/useAthleteRaceHistory";

const { apiClient } = clientModule as unknown as {
  apiClient: { get: ReturnType<typeof vi.fn> };
};

function makeWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  return { wrapper, queryClient };
}

describe("useAthleteRaceHistory — seriesKind", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    apiClient.get.mockResolvedValue({
      data: { points: [], seasons: [], caveats: [] },
    });
  });

  it("por defecto no envía series_kind (el backend asume `cup`)", async () => {
    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useAthleteRaceHistory(42), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/athletes/42/race-analysis/history",
      expect.objectContaining({ params: {} }),
    );
  });

  it.each(["all", "championship"] as const)(
    "envía series_kind=%s cuando se pide",
    async (kind) => {
      const { wrapper } = makeWrapper();
      const { result } = renderHook(() => useAthleteRaceHistory(42, kind), {
        wrapper,
      });
      await waitFor(() => expect(result.current.isSuccess).toBe(true));

      expect(apiClient.get).toHaveBeenCalledWith(
        "/api/athletes/42/race-analysis/history",
        expect.objectContaining({ params: { series_kind: kind } }),
      );
    },
  );

  it("cada variante tiene su propia clave, bajo el prefijo del atleta", async () => {
    const { wrapper, queryClient } = makeWrapper();
    const cup = renderHook(() => useAthleteRaceHistory(42), { wrapper });
    const all = renderHook(() => useAthleteRaceHistory(42, "all"), { wrapper });
    await waitFor(() => {
      expect(cup.result.current.isSuccess).toBe(true);
      expect(all.result.current.isSuccess).toBe(true);
    });

    const keys = queryClient
      .getQueryCache()
      .findAll({ queryKey: ["athlete-race-history", 42] })
      .map((q) => q.queryKey);
    expect(keys).toEqual(
      expect.arrayContaining([
        ["athlete-race-history", 42, "cup"],
        ["athlete-race-history", 42, "all"],
      ]),
    );
    expect(apiClient.get).toHaveBeenCalledTimes(2);
  });

  it("no consulta con un id inválido", () => {
    const { wrapper } = makeWrapper();
    renderHook(() => useAthleteRaceHistory(null, "all"), { wrapper });
    expect(apiClient.get).not.toHaveBeenCalled();
  });
});
