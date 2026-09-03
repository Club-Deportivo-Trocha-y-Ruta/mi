/**
 * Tests vitest para useUpdateStageLog (feature 038, T204).
 *
 * Cubre: happy path del PATCH con los campos nuevos de la bitácora, e
 * invalidación de las query keys correctas.
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
import { newsletterHandlers } from "@/test/msw/newsletterHandlers";
import { useUpdateStageLog } from "@/hooks/training/useUpdateStageLog";

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

describe("useUpdateStageLog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...newsletterHandlers);
  });

  it("mutate() envía stage_overrides/hidden_blocks/coach_note vía PATCH", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateStageLog(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({
        stage_overrides: { stage_title: "Título editado" },
        hidden_blocks: ["photos"],
        coach_note: "Nota del coach",
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(1);
    expect(result.current.data?.athlete_id).toBe(42);
  });

  it("onSuccess invalida detalle y lista del mismo atleta/boletín", async () => {
    const { Wrapper, qc } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateStageLog(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ coach_note: "Nota del coach" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["athlete-newsletter", 1, 42, 1] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["athlete-newsletters", 1, 42] }),
    );
  });

  it("propaga 409 cuando el boletín no admite edición", async () => {
    const { http, HttpResponse } = await import("msw");
    mswServer.use(
      http.patch(
        "*/api/athletes/:athleteId/monthly-newsletters/:id",
        () =>
          HttpResponse.json(
            { detail: "El boletín ya fue enviado." },
            { status: 409 },
          ),
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useUpdateStageLog(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ coach_note: "Nota" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as { response?: { status: number } };
    expect(err?.response?.status).toBe(409);
  });
});
