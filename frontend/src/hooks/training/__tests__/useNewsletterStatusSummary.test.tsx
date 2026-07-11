/**
 * Tests vitest para useNewsletterStatusSummary.
 *
 * Cubre:
 *  - queryFn happy path: devuelve NewsletterStatusSummary del backend.
 *  - queryKey exacta ["newsletter-status-summary", userId, year, month] (privacy R2).
 *  - year/month se envían como query params al endpoint de resumen.
 *  - enabled=false (sin accessToken, o sin year/month) no dispara la petición.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

import { mswServer } from "@/test/setup";
import type { NewsletterStatusSummary } from "@/hooks/training/useNewsletterStatusSummary";

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

import { useNewsletterStatusSummary } from "@/hooks/training/useNewsletterStatusSummary";

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeSummary(
  overrides?: Partial<NewsletterStatusSummary>,
): NewsletterStatusSummary {
  return {
    year: 2026,
    month: 6,
    items: [
      {
        athlete_id: 42,
        newsletter_id: 1,
        status: "sent",
        generated_at: "2026-06-01T00:00:00Z",
        sent_at: "2026-06-02T10:00:00Z",
      },
      {
        athlete_id: 43,
        newsletter_id: 2,
        status: "draft",
        generated_at: "2026-06-01T00:00:00Z",
        sent_at: null,
      },
    ],
    ...overrides,
  };
}

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0, staleTime: 0 } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  }
  return { Wrapper, qc };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("useNewsletterStatusSummary", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthState.accessToken = "test-token";
    mockAuthState.user = { id: 7 };
  });

  it("devuelve el NewsletterStatusSummary del backend (happy path)", async () => {
    const summary = makeSummary();
    mswServer.use(
      http.get("*/api/training/athlete-newsletters/summary", () =>
        HttpResponse.json(summary),
      ),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useNewsletterStatusSummary(2026, 6), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(result.current.data).toEqual(summary);
  });

  it("envía year/month como query params al endpoint de resumen", async () => {
    let receivedYear: string | null = null;
    let receivedMonth: string | null = null;
    mswServer.use(
      http.get("*/api/training/athlete-newsletters/summary", ({ request }) => {
        const url = new URL(request.url);
        receivedYear = url.searchParams.get("year");
        receivedMonth = url.searchParams.get("month");
        return HttpResponse.json(makeSummary());
      }),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useNewsletterStatusSummary(2026, 4), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(receivedYear).toBe("2026");
    expect(receivedMonth).toBe("4");
  });

  it("usa la queryKey ['newsletter-status-summary', userId, year, month] (privacy R2)", async () => {
    mswServer.use(
      http.get("*/api/training/athlete-newsletters/summary", () =>
        HttpResponse.json(makeSummary()),
      ),
    );

    const { Wrapper, qc } = makeWrapper();
    const { result } = renderHook(() => useNewsletterStatusSummary(2026, 6), {
      wrapper: Wrapper,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    expect(qc.getQueryData(["newsletter-status-summary", 7, 2026, 6])).toEqual(
      makeSummary(),
    );
  });

  it("NO dispara la petición cuando year/month son undefined", async () => {
    let callCount = 0;
    mswServer.use(
      http.get("*/api/training/athlete-newsletters/summary", () => {
        callCount += 1;
        return HttpResponse.json(makeSummary());
      }),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(
      () => useNewsletterStatusSummary(undefined, undefined),
      { wrapper: Wrapper },
    );

    // Da tiempo a que, si estuviera mal condicionado, la petición se disparara.
    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(result.current.fetchStatus).toBe("idle");
    expect(result.current.isPending).toBe(true);
    expect(callCount).toBe(0);
  });

  it("NO dispara la petición cuando no hay accessToken", async () => {
    mockAuthState.accessToken = null;
    let callCount = 0;
    mswServer.use(
      http.get("*/api/training/athlete-newsletters/summary", () => {
        callCount += 1;
        return HttpResponse.json(makeSummary());
      }),
    );

    const { Wrapper } = makeWrapper();
    const { result } = renderHook(() => useNewsletterStatusSummary(2026, 6), {
      wrapper: Wrapper,
    });

    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(result.current.fetchStatus).toBe("idle");
    expect(callCount).toBe(0);
  });
});
