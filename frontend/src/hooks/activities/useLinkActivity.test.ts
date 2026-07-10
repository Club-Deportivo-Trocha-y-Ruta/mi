/**
 * Tests de useLinkActivity — invalidaciones de caché tras enlazar/desenlazar
 * una actividad (feature 025, T032; extendido en
 * specs/025-strava-activity-sync/session-detail-redesign.md §3.5 para
 * invalidar también `unlinked-activities-near-date`, la query que alimenta
 * el estado "sin enlazar" del `ActivityEvidenceStrip` en `SessionDetailPage`).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/stravaActivities", () => ({
  linkActivity: vi.fn(),
}));

import { linkActivity } from "@/api/stravaActivities";
import { useLinkActivity } from "./useLinkActivity";
import { mockActivity } from "@/test/msw/stravaHandlers";

function wrapper(queryClient: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return createElement(QueryClientProvider, { client: queryClient }, children);
  };
}

beforeEach(() => {
  vi.mocked(linkActivity).mockResolvedValue(mockActivity());
});

describe("useLinkActivity — invalidaciones on success", () => {
  it("invalida activities-review, athlete-activities, session-activities y unlinked-activities-near-date", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useLinkActivity(), {
      wrapper: wrapper(queryClient),
    });

    result.current.mutate({
      activityId: 5,
      trainingSessionId: 10,
      athleteId: 42,
      previousSessionId: null,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey,
    );

    expect(invalidatedKeys).toContainEqual(["activities-review"]);
    expect(invalidatedKeys).toContainEqual(["athlete-activities", 42]);
    expect(invalidatedKeys).toContainEqual(["session-activities", 10]);
    expect(invalidatedKeys).toContainEqual(["unlinked-activities-near-date"]);
  });

  it("también invalida unlinked-activities-near-date al desenlazar (trainingSessionId=null)", async () => {
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useLinkActivity(), {
      wrapper: wrapper(queryClient),
    });

    result.current.mutate({
      activityId: 5,
      trainingSessionId: null,
      athleteId: 42,
      previousSessionId: 10,
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    const invalidatedKeys = invalidateSpy.mock.calls.map(
      (call) => (call[0] as { queryKey: unknown[] }).queryKey,
    );

    expect(invalidatedKeys).toContainEqual(["unlinked-activities-near-date"]);
    expect(invalidatedKeys).toContainEqual(["session-activities", 10]);
  });
});
