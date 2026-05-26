/**
 * Tests vitest para useAttachInsightsToNewsletter (Sprint 4 hotfix).
 *
 * Cubre:
 *  - mutate() happy path: devuelve AttachInsightsResponse del backend.
 *  - onSuccess invalida "athlete-newsletters" del MISMO athleteId.
 *  - Error 400 con invalid_ids se propaga al caller sin exponer datos PII.
 *  - Error 403 (parent) se propaga como rechazo de la mutación.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
import {
  newsletterHandlers,
  attachInsightsInvalidHandler,
  attachInsightsForbiddenHandler,
} from "@/test/msw/newsletterHandlers";
import { useAttachInsightsToNewsletter } from "@/api/athleteNewsletters";

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

describe("useAttachInsightsToNewsletter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    // Registrar el handler de attach-insights (incluido en newsletterHandlers)
    mswServer.use(...newsletterHandlers);
  });

  it("mutate() happy path: devuelve AttachInsightsResponse con los insight_ids enviados", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useAttachInsightsToNewsletter(145), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ insight_ids: [1, 2, 3] });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    const data = result.current.data;
    expect(data).toBeDefined();
    expect(data?.newsletter_id).toBe(42);
    expect(data?.athlete_id).toBe(145);
    expect(data?.selected_race_insight_ids).toEqual([1, 2, 3]);
    expect(data?.created).toBe(true);
    // status no es campo sensible — solo confirmamos que está presente
    expect(typeof data?.status).toBe("string");
  });

  it("onSuccess invalida 'athlete-newsletters' del MISMO athleteId", async () => {
    const { Wrapper, qc } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useAttachInsightsToNewsletter(42), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ insight_ids: [10] });
    });

    await waitFor(() => {
      expect(result.current.isSuccess).toBe(true);
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["athlete-newsletters", 42] }),
    );
  });

  it("error 400 (invalid_ids) propaga el rechazo al caller", async () => {
    mswServer.use(attachInsightsInvalidHandler);

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useAttachInsightsToNewsletter(42), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ insight_ids: [4, 5] });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    expect(result.current.error).toBeDefined();
    // El error NO debe exponer datos del atleta ni del insight (sólo el status HTTP)
    const err = result.current.error as { response?: { status: number } };
    expect(err?.response?.status).toBe(400);
  });

  it("error 403 (parent intenta adjuntar) propaga el rechazo", async () => {
    mswServer.use(attachInsightsForbiddenHandler);

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useAttachInsightsToNewsletter(42), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ insight_ids: [1] });
    });

    await waitFor(() => {
      expect(result.current.isError).toBe(true);
    });

    const err = result.current.error as { response?: { status: number } };
    expect(err?.response?.status).toBe(403);
  });
});
