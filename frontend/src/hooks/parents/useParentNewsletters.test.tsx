/**
 * Tests vitest para useParentNewsletters (feature 038, T204).
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
import { stageLogHandlers } from "@/test/msw/stageLogHandlers";
import { useParentNewsletters } from "@/hooks/parents/useParentNewsletters";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

describe("useParentNewsletters", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mswServer.use(...stageLogHandlers);
  });

  it("devuelve la lista de boletines enviados del atleta", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useParentNewsletters(42), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toHaveLength(2);
    expect(result.current.data?.[0].athlete_id).toBe(42);
  });

  it("no dispara la query cuando athleteId es undefined", () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useParentNewsletters(undefined), {
      wrapper: Wrapper,
    });

    expect(result.current.fetchStatus).toBe("idle");
  });

  it("usa userId al inicio del queryKey (privacy R2)", async () => {
    const { Wrapper, qc } = makeWrapper();
    renderHook(() => useParentNewsletters(42), { wrapper: Wrapper });

    await waitFor(() => {
      const state = qc.getQueryState(["parent-newsletters", 5, 42]);
      expect(state?.status).toBe("success");
    });
  });
});
