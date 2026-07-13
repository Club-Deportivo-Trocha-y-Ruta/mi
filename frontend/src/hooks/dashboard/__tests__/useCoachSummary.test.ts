/**
 * Tests vitest para useCoachSummary (feature 031).
 *
 * Cubre:
 *  - queryFn happy path: devuelve CoachSummary del backend (escenario feliz,
 *    todos los campos poblados).
 *  - queryKey exacta ["dashboard", "coach-summary"].
 *  - refetchOnMount: "always" (research.md R8): un remount con datos ya en
 *    caché (dentro del staleTime de 60s) igual dispara un nuevo fetch.
 *  - degradado parcial: un campo en null, los otros dos siguen poblados
 *    (FR-004).
 *  - enabled=false (sin accessToken) no dispara la petición.
 *  - RBAC 403 se propaga como error del hook.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { createElement, type ReactNode } from "react";

import { mswServer } from "@/test/setup";
import {
  dashboardHandlers,
  coachSummaryPartialNullHandler,
  coachSummaryForbiddenHandler,
  makeCoachSummary,
} from "@/test/msw/dashboardHandlers";

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

const mockAuthState: {
  accessToken: string | null;
  user: { id: number } | null;
} = {
  accessToken: "test-token",
  user: { id: 7 },
};

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) => sel(mockAuthState)),
}));

import { useCoachSummary } from "@/hooks/dashboard/useCoachSummary";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeWrapper(qc?: QueryClient) {
  const client =
    qc ?? new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client }, children);
  }
  return { Wrapper, qc: client };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useCoachSummary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.accessToken = "test-token";
    mockAuthState.user = { id: 7 };
  });

  it("devuelve el CoachSummary del backend (happy path, todos los campos poblados)", async () => {
    mswServer.use(...dashboardHandlers);

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCoachSummary(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(makeCoachSummary());
  });

  it('usa la queryKey ["dashboard", "coach-summary"]', async () => {
    mswServer.use(...dashboardHandlers);

    const { Wrapper, qc } = makeWrapper();
    const { result } = renderHook(() => useCoachSummary(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(qc.getQueryData(["dashboard", "coach-summary"])).toEqual(
      makeCoachSummary(),
    );
  });

  it('refetchOnMount: "always" dispara un nuevo fetch en cada remount, incluso con datos frescos en caché', async () => {
    let callCount = 0;
    mswServer.use(
      http.get("*/api/dashboard/coach-summary", () => {
        callCount += 1;
        return HttpResponse.json(makeCoachSummary());
      }),
    );

    // Un único QueryClient compartido entre ambos renders: si el cache
    // reutilizara los datos previos (staleTime: 60_000 aún vigente), el
    // segundo mount no debería refetchear salvo por `refetchOnMount: "always"`.
    const { Wrapper, qc } = makeWrapper();

    const first = renderHook(() => useCoachSummary(), { wrapper: Wrapper });
    await waitFor(() => expect(first.result.current.isSuccess).toBe(true));
    expect(callCount).toBe(1);

    first.unmount();

    const second = renderHook(() => useCoachSummary(), {
      wrapper: makeWrapper(qc).Wrapper,
    });
    await waitFor(() => expect(second.result.current.isSuccess).toBe(true));
    expect(callCount).toBe(2);
  });

  it("degradado parcial: un campo en null, los otros dos siguen poblados (FR-004)", async () => {
    mswServer.use(coachSummaryPartialNullHandler);

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCoachSummary(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.weekly_load).toBeNull();
    expect(result.current.data?.consents_pending).toBe(3);
    expect(result.current.data?.insights_stale).toBe(1);
  });

  it("NO dispara la petición cuando no hay accessToken", async () => {
    mockAuthState.accessToken = null;
    let callCount = 0;
    mswServer.use(
      http.get("*/api/dashboard/coach-summary", () => {
        callCount += 1;
        return HttpResponse.json(makeCoachSummary());
      }),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCoachSummary(), { wrapper: Wrapper });

    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(result.current.fetchStatus).toBe("idle");
    expect(callCount).toBe(0);
  });

  it("RBAC 403 se propaga como error del hook", async () => {
    mswServer.use(coachSummaryForbiddenHandler);

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useCoachSummary(), { wrapper: Wrapper });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});
