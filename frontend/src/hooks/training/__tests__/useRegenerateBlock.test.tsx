/**
 * Tests vitest para useRegenerateBlock (feature 038, T204).
 *
 * Cubre: happy path, invalidación de ["athlete-newsletter", userId, ...] y
 * ["athlete-newsletters", userId, ...], y errores 409/451/503.
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
  stageLogHandlers,
  regenerateBlockSentConflictHandler,
  regenerateBlockConsentMissingHandler,
  regenerateBlockProviderErrorHandler,
} from "@/test/msw/stageLogHandlers";
import { useRegenerateBlock } from "@/hooks/training/useRegenerateBlock";

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

describe("useRegenerateBlock", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...stageLogHandlers);
  });

  it("mutate() happy path: devuelve el AthleteNewsletter actualizado", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBlock(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ block: "stage_title" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.stage_log).not.toBeNull();
  });

  it("onSuccess invalida las query keys de detalle y lista del mismo atleta/boletín", async () => {
    const { Wrapper, qc } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useRegenerateBlock(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ block: "observations", instruction: "más corto" });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["athlete-newsletter", 1, 42, 1] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["athlete-newsletters", 1, 42] }),
    );
  });

  it("propaga 409 cuando el boletín ya fue enviado", async () => {
    mswServer.use(regenerateBlockSentConflictHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBlock(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ block: "stage_title" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as { response?: { status: number } };
    expect(err?.response?.status).toBe(409);
  });

  it("propaga 451 cuando falta el consentimiento de IA", async () => {
    mswServer.use(regenerateBlockConsentMissingHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBlock(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ block: "family_compass" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as { response?: { status: number } };
    expect(err?.response?.status).toBe(451);
  });

  it("propaga 503 cuando el proveedor de IA falla", async () => {
    mswServer.use(regenerateBlockProviderErrorHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useRegenerateBlock(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate({ block: "next_segment_text" });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as { response?: { status: number } };
    expect(err?.response?.status).toBe(503);
  });
});
