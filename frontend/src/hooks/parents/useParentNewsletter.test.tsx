/**
 * Tests vitest para useParentNewsletter (feature 038, T204).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 5, role: "parent" },
      isAuthenticated: true,
    }),
  ),
}));

import { mswServer } from "@/test/setup";
import {
  stageLogHandlers,
  parentNewsletterNotFoundHandler,
} from "@/test/msw/stageLogHandlers";
import { useParentNewsletter } from "@/hooks/parents/useParentNewsletter";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("useParentNewsletter", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...stageLogHandlers);
  });

  it("devuelve el detalle con stage_log ya filtrado (sin block_states)", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useParentNewsletter(42, 1), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data?.id).toBe(1);
    expect(result.current.data?.stage_log).not.toHaveProperty("block_states");
  });

  it("no dispara la query cuando falta athleteId o newsletterId", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useParentNewsletter(undefined, undefined), {
      wrapper: Wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("propaga 404 cuando el boletín no fue enviado o no está vinculado", async () => {
    mswServer.use(parentNewsletterNotFoundHandler);
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useParentNewsletter(42, 999), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const err = result.current.error as { response?: { status: number } };
    expect(err?.response?.status).toBe(404);
  });
});
