/**
 * Tests vitest para useClubInsightsByRace (Sprint 3).
 *
 * Cubre:
 *  - Loading → data con la respuesta del handler MSW.
 *  - Error state cuando el endpoint responde 500.
 *  - Hook deshabilitado cuando raceEventId es null o NaN.
 *  - queryKey incluye opts para refetch cuando cambian los params.
 */
import { describe, it, expect } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";

import { mswServer } from "@/test/setup";
import { useClubInsightsByRace } from "@/hooks/athletes/useClubInsightsByRace";

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useClubInsightsByRace", () => {
  it("devuelve datos del handler MSW default", async () => {
    const { result } = renderHook(() => useClubInsightsByRace(4), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.race_event_id).toBe(4);
    expect(result.current.data?.total_athletes).toBe(3);
    expect(result.current.data?.items).toHaveLength(3);
  });

  it("expone isError cuando el endpoint responde 500", async () => {
    mswServer.use(
      http.get(
        "*/api/races/:raceEventId/club-insights",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    const { result } = renderHook(() => useClubInsightsByRace(4), {
      wrapper: makeWrapper(),
    });
    await waitFor(() => expect(result.current.isError).toBe(true), {
      timeout: 3000,
    });
  });

  it("queda deshabilitado cuando raceEventId es null", () => {
    const { result } = renderHook(() => useClubInsightsByRace(null), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("queda deshabilitado cuando raceEventId es NaN", () => {
    const { result } = renderHook(() => useClubInsightsByRace(NaN), {
      wrapper: makeWrapper(),
    });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("pasa clubId y latestOnly como query params al endpoint", async () => {
    const observed: string[] = [];
    mswServer.use(
      http.get(
        "*/api/races/:raceEventId/club-insights",
        ({ request }) => {
          const url = new URL(request.url);
          observed.push(url.search);
          return HttpResponse.json({
            race_event_id: 4,
            race_event_label: "Válida 4",
            total_athletes: 0,
            items: [],
          });
        },
      ),
    );
    const { result } = renderHook(
      () => useClubInsightsByRace(4, { clubId: 1, latestOnly: true, limit: 20 }),
      { wrapper: makeWrapper() },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observed[0]).toContain("club_id=1");
    expect(observed[0]).toContain("latest_only=true");
    expect(observed[0]).toContain("limit=20");
  });

  it("refetch cuando cambia raceEventId (queryKey distinto)", async () => {
    const observed: number[] = [];
    mswServer.use(
      http.get(
        "*/api/races/:raceEventId/club-insights",
        ({ params }) => {
          observed.push(Number(params.raceEventId));
          return HttpResponse.json({
            race_event_id: Number(params.raceEventId),
            race_event_label: `Válida ${params.raceEventId}`,
            total_athletes: 0,
            items: [],
          });
        },
      ),
    );
    const wrapper = makeWrapper();
    const { result, rerender } = renderHook(
      ({ id }: { id: number }) => useClubInsightsByRace(id),
      { wrapper, initialProps: { id: 3 } },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(observed).toContain(3);

    rerender({ id: 5 });
    await waitFor(() => expect(observed).toContain(5));
  });
});
