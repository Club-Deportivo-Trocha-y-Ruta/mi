/**
 * Tests de `usePendingAnalyses` / `useDismissStaleRun` (feature 045, US5).
 *
 * Cubre: `state` obligatorio en la petición, `season` solo cuando se pide,
 * queryKey sin PII, deshabilitado sin sesión, y que descartar un aviso
 * refresca la lista pendiente y el resumen del Home — también ante un 409.
 */
import { describe, expect, it, vi } from "vitest";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import {
  dismissStaleConflictHandler,
  pendingAnalysesHandlers,
  pendingAnalysesErrorHandler,
} from "@/test/msw/racePendingAnalysesHandlers";

const mockAuthState: { accessToken: string | null } = { accessToken: "test-token" };

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) => sel(mockAuthState)),
}));

import {
  pendingAnalysesKeys,
  useDismissStaleRun,
  usePendingAnalyses,
} from "@/hooks/race/usePendingAnalyses";

function makeWrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children);
  }
  return { Wrapper, client };
}

describe("usePendingAnalyses", () => {
  it("pide state y devuelve la lista (más recientes primero, tal como la sirve el backend)", async () => {
    mswServer.use(...pendingAnalysesHandlers);
    const { Wrapper } = makeWrapper();

    const { result } = renderHook(() => usePendingAnalyses({ state: "stale" }), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.map((i) => i.run_id)).toEqual([
      "run-stale-001",
      "run-stale-002",
    ]);
  });

  it("envía season solo cuando se indica", async () => {
    const seen: string[] = [];
    mswServer.use(
      http.get("*/api/race-analysis/pending-analyses", ({ request }) => {
        seen.push(new URL(request.url).search);
        return HttpResponse.json([]);
      }),
    );
    const { Wrapper } = makeWrapper();

    const first = renderHook(() => usePendingAnalyses({ state: "awaiting_approval" }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    const second = renderHook(
      () => usePendingAnalyses({ state: "awaiting_approval", season: 2026 }),
      { wrapper: Wrapper },
    );
    await waitFor(() => expect(second.result.current.isSuccess).toBe(true));

    expect(seen).toContain("?state=awaiting_approval");
    expect(seen).toContain("?state=awaiting_approval&season=2026");
  });

  it("la queryKey lleva solo state y season (sin datos del deportista)", () => {
    expect(pendingAnalysesKeys.list("stale", null)).toEqual(["race-pending-analyses", "stale", null]);
    expect(pendingAnalysesKeys.list("awaiting_approval", 2026)).toEqual([
      "race-pending-analyses",
      "awaiting_approval",
      2026,
    ]);
  });

  it("queda deshabilitada sin sesión", () => {
    mockAuthState.accessToken = null;
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => usePendingAnalyses({ state: "stale" }), {
      wrapper: Wrapper,
    });
    expect(result.current.fetchStatus).toBe("idle");
    mockAuthState.accessToken = "test-token";
  });

  it("un fallo del servidor deja la query en error", async () => {
    mswServer.use(pendingAnalysesErrorHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => usePendingAnalyses({ state: "stale" }), {
      wrapper: Wrapper,
    });
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useDismissStaleRun", () => {
  it("al descartar, invalida la lista pendiente y el resumen del Home", async () => {
    mswServer.use(...pendingAnalysesHandlers);
    const { Wrapper, client } = makeWrapper();
    const spy = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useDismissStaleRun(), { wrapper: Wrapper });
    await act(async () => {
      await result.current.mutateAsync({ runId: "run-stale-001", athleteId: 144 });
    });

    const predicate = spy.mock.calls[0]?.[0]?.predicate as (q: { queryKey: unknown }) => boolean;
    expect(predicate({ queryKey: ["race-pending-analyses", "stale", null] })).toBe(true);
    expect(predicate({ queryKey: ["dashboard", "coach-summary"] })).toBe(true);
    expect(predicate({ queryKey: ["athlete-insights", 144, {}] })).toBe(true);
    // Otro atleta no se refresca.
    expect(predicate({ queryKey: ["athlete-insights", 999, {}] })).toBe(false);
  });

  it("un 409 (ya no está desactualizado) también refresca la lista", async () => {
    mswServer.use(dismissStaleConflictHandler);
    const { Wrapper, client } = makeWrapper();
    const spy = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useDismissStaleRun(), { wrapper: Wrapper });
    await act(async () => {
      await expect(
        result.current.mutateAsync({ runId: "run-stale-001", athleteId: 144 }),
      ).rejects.toBeTruthy();
    });

    expect(spy).toHaveBeenCalled();
  });
});
