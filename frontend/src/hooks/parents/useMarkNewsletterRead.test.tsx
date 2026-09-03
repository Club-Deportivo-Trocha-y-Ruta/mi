/**
 * Tests vitest para useMarkNewsletterRead (feature 038, T204).
 *
 * Cubre: happy path, invalidación de query keys correctas, y que solo
 * dispara el request una vez por newsletterId por sesión de navegador
 * (sessionStorage["bitacora-read:<id>"]).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
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
import {
  useMarkNewsletterRead,
  wasNewsletterMarkedReadThisSession,
} from "@/hooks/parents/useMarkNewsletterRead";

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

describe("useMarkNewsletterRead", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    sessionStorage.clear();
    mswServer.use(...stageLogHandlers);
  });

  it("mutate() marca la sesión como leída tras el 204", async () => {
    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMarkNewsletterRead(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(wasNewsletterMarkedReadThisSession(1)).toBe(true);
  });

  it("onSuccess invalida detalle, lista y my-athletes (contador de no leídos)", async () => {
    const { Wrapper, qc } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useMarkNewsletterRead(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["parent-newsletter", 5, 42, 1] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["parent-newsletters", 5, 42] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["my-athletes", 5] }),
    );
  });

  it("no repite el POST si ya se marcó como leído en esta sesión", async () => {
    sessionStorage.setItem("bitacora-read:1", "1");
    const { http, HttpResponse } = await import("msw");
    let callCount = 0;
    mswServer.use(
      http.post(
        "*/api/parents/me/athletes/:athleteId/newsletters/:newsletterId/read",
        () => {
          callCount += 1;
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useMarkNewsletterRead(42, 1), {
      wrapper: Wrapper,
    });

    act(() => {
      result.current.mutate();
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(callCount).toBe(0);
  });
});
