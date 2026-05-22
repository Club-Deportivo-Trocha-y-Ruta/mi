/**
 * Tests vitest para useLaunchAthleteAnalysis (FE-3).
 *
 * Cubre:
 *  - mutateAsync devuelve la respuesta del backend con run_id.
 *  - onSuccess invalida queries de runs/insights del MISMO athleteId.
 *  - No invalida queries de OTROS athleteIds (defensa cross-athlete).
 *  - Error state se propaga al caller.
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
import { useLaunchAthleteAnalysis } from "@/hooks/athletes/useLaunchAthleteAnalysis";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0, staleTime: 0 },
      mutations: { retry: false },
    },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("useLaunchAthleteAnalysis", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("mutateAsync devuelve el run_id devuelto por el backend", async () => {
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        () =>
          HttpResponse.json(
            {
              run_id: "run-success-1",
              status: "running",
              started_at: "2026-05-22T10:00:00Z",
              status_url: "/x",
              estimated_seconds: 30,
            },
            { status: 201 },
          ),
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLaunchAthleteAnalysis(42), {
      wrapper: Wrapper,
    });

    const response = await result.current.mutateAsync({
      season: 2026,
      valida_nums: [4],
      explain_mode: false,
    });

    expect(response.run_id).toBe("run-success-1");
    expect(response.status).toBe("running");
  });

  it("invalida queries de runs/insights del MISMO athleteId", async () => {
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        () =>
          HttpResponse.json(
            {
              run_id: "r1",
              status: "running",
              started_at: "2026-05-22T10:00:00Z",
              status_url: "/x",
              estimated_seconds: 30,
            },
            { status: 201 },
          ),
      ),
    );

    const { Wrapper, qc } = makeWrapper();

    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useLaunchAthleteAnalysis(42), {
      wrapper: Wrapper,
    });

    await result.current.mutateAsync({
      season: 2026,
      explain_mode: false,
    });

    // Verifica que invalidateQueries fue llamado con un predicate
    await waitFor(() => {
      expect(invalidateSpy).toHaveBeenCalled();
    });
    const call = invalidateSpy.mock.calls[0]?.[0] as {
      predicate?: (q: { queryKey: unknown }) => boolean;
    };
    expect(typeof call.predicate).toBe("function");

    // Simula el matching del predicate con queries del 42 y del 99
    const predicate = call.predicate!;
    expect(
      predicate({ queryKey: ["athlete-runs", 42, {}] } as never),
    ).toBe(true);
    expect(
      predicate({ queryKey: ["athlete-insights", 42, {}] } as never),
    ).toBe(true);
    // ATHLETE DISTINTO — no debe ser invalidado
    expect(
      predicate({ queryKey: ["athlete-runs", 99, {}] } as never),
    ).toBe(false);
    expect(
      predicate({ queryKey: ["athlete-insights", 99, {}] } as never),
    ).toBe(false);
    // OTRO query base — no debe ser invalidado
    expect(
      predicate({ queryKey: ["athlete-evolution", 42, 2026, "ranking"] } as never),
    ).toBe(false);
  });

  it("propaga error cuando el backend responde 400", async () => {
    mswServer.use(
      http.post(
        "*/api/athletes/:athleteId/race-analysis/runs",
        () =>
          new HttpResponse(
            JSON.stringify({ detail: "Season requerida" }),
            { status: 400 },
          ),
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useLaunchAthleteAnalysis(42), {
      wrapper: Wrapper,
    });

    await expect(
      result.current.mutateAsync({
        season: 2026,
        explain_mode: false,
      } as never),
    ).rejects.toThrow();
  });
});
