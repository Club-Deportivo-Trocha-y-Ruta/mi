/**
 * Tests vitest para useAthleteInsights (FE-3).
 *
 * Cubre:
 *  - Pasa params correctamente al endpoint (verifica query string MSW).
 *  - Refetch cuando los params cambian (queryKey re-deriva).
 *  - Error state expone el error de TanStack Query.
 *  - Hook deshabilitado cuando athleteId<=0 o no hay accessToken.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach" },
      isAuthenticated: true,
    }),
  ),
}));

import { mswServer } from "@/test/setup";
import { mockInsight } from "@/test/msw/athleteRaceAnalysisHandlers";
import { useAthleteInsights } from "@/hooks/athletes/useAthleteInsights";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useAthleteInsights", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("pasa params como query string correcto", async () => {
    const observed: string[] = [];
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        ({ request }) => {
          const url = new URL(request.url);
          observed.push(url.search);
          return HttpResponse.json({
            items: [mockInsight()],
            total: 1,
            limit: 1,
            offset: 0,
          });
        },
      ),
    );
    const { result } = renderHook(
      () =>
        useAthleteInsights(42, {
          season: 2026,
          valida_num: 4,
          latest_only: true,
          limit: 1,
        }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observed[0]).toContain("season=2026");
    expect(observed[0]).toContain("valida_num=4");
    expect(observed[0]).toContain("latest_only=true");
    expect(observed[0]).toContain("limit=1");
  });

  it("expone error state cuando el endpoint responde 500", async () => {
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    const { result } = renderHook(() => useAthleteInsights(42), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true), {
      timeout: 3000,
    });
  });

  it("queda deshabilitado cuando athleteId<=0", () => {
    const { result } = renderHook(() => useAthleteInsights(0), {
      wrapper: makeWrapper(),
    });
    // enabled=false → fetchStatus="idle" y no hay refetch automático
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("refetch cuando cambian los params (queryKey distinto)", async () => {
    const observed: string[] = [];
    mswServer.use(
      http.get(
        "*/api/athletes/:athleteId/race-analysis/insights",
        ({ request }) => {
          const url = new URL(request.url);
          observed.push(url.search);
          return HttpResponse.json({
            items: [],
            total: 0,
            limit: 50,
            offset: 0,
          });
        },
      ),
    );

    const wrapper = makeWrapper();
    const { result, rerender } = renderHook(
      ({ season }: { season: number }) =>
        useAthleteInsights(42, { season, latest_only: true }),
      { wrapper, initialProps: { season: 2025 } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observed.some((s) => s.includes("season=2025"))).toBe(true);

    rerender({ season: 2026 });
    await waitFor(() => {
      expect(observed.some((s) => s.includes("season=2026"))).toBe(true);
    });
  });
});
