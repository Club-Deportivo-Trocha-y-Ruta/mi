/**
 * Tests T044 — useLinkCalendarEvent hook (Wave E, US5, FR-025).
 *
 * Verifica:
 *   1. La mutación dispara POST /race-events/{id}/calendar-link con el body correcto.
 *   2. On success invalida raceEventKeys.detail y raceEventKeys.lists.
 *   3. On success invalida el árbol del calendario (includeCalendar=true).
 *   4. 409 de backend se propaga como error de la mutación.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, act } from "@testing-library/react";
import { createElement } from "react";
import { describe, expect, it, vi, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";

vi.mock("@/store/auth.store", () => ({
  useAuthStore: vi.fn((sel: (s: unknown) => unknown) =>
    sel({
      accessToken: "test-token",
      user: { id: 1, role: "coach", first_name: "C", last_name: "T" },
      isAuthenticated: true,
    }),
  ),
}));

import { mswServer } from "@/test/setup";
import {
  raceEventsHandlers,
  raceEventsCalendarLinkConflictHandler,
} from "@/test/msw/raceEventsHandlers";
import { useLinkCalendarEvent, raceEventKeys } from "@/hooks/race/useRaceEvents";

// ── Helpers ──────────────────────────────────────────────────────────────────

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return {
    wrapper: ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children),
    queryClient,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  mswServer.use(...raceEventsHandlers);
});

// ── Suite ─────────────────────────────────────────────────────────────────────

describe("useLinkCalendarEvent — T044", () => {
  it("dispara POST /{raceEventId}/calendar-link con body correcto", async () => {
    let capturedBody: Record<string, unknown> | null = null;

    mswServer.use(
      http.post(
        "*/api/race-analysis/race-events/:id/calendar-link",
        async ({ request }) => {
          capturedBody = (await request.json()) as Record<string, unknown>;
          return HttpResponse.json({ id: 7, has_calendar_event: true });
        },
      ),
    );

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLinkCalendarEvent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        raceEventId: 7,
        body: { calendar_event_id: 301 },
      });
    });

    expect(capturedBody).toEqual({ calendar_event_id: 301 });
  });

  it("retorna { id, has_calendar_event: true } en success", async () => {
    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLinkCalendarEvent(), { wrapper });

    let data: unknown;
    await act(async () => {
      data = await result.current.mutateAsync({
        raceEventId: 5,
        body: { calendar_event_id: 200 },
      });
    });

    expect(data).toEqual({ id: 5, has_calendar_event: true });
  });

  it("on success invalida raceEventKeys.detail y raceEventKeys.lists", async () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useLinkCalendarEvent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        raceEventId: 7,
        body: { calendar_event_id: 301 },
      });
    });

    await waitFor(() => {
      const calls = invalidateSpy.mock.calls.map((c) => c[0]);
      // debe invalidar el detalle del evento específico
      expect(calls).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ queryKey: raceEventKeys.detail(7) }),
        ]),
      );
      // debe invalidar todas las listas
      expect(calls).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ queryKey: raceEventKeys.lists() }),
        ]),
      );
    });
  });

  it("on success invalida el árbol del calendario (calendarQueryRoot)", async () => {
    const { wrapper, queryClient } = createWrapper();
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");

    const { result } = renderHook(() => useLinkCalendarEvent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        raceEventId: 7,
        body: { calendar_event_id: 301 },
      });
    });

    await waitFor(() => {
      const queriedKeys = invalidateSpy.mock.calls.map((c) => c[0]);
      // La invalidación del calendario usa queryKey: ["calendar"]
      expect(queriedKeys).toEqual(
        expect.arrayContaining([
          expect.objectContaining({ queryKey: ["calendar"] }),
        ]),
      );
    });
  });

  it("propaga el error 409 (ya vinculada) como error de la mutación", async () => {
    mswServer.use(raceEventsCalendarLinkConflictHandler);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useLinkCalendarEvent(), { wrapper });

    let caughtError: unknown;
    await act(async () => {
      try {
        await result.current.mutateAsync({
          raceEventId: 3,
          body: { calendar_event_id: 999 },
        });
      } catch (e) {
        caughtError = e;
      }
    });

    expect(caughtError).toBeDefined();
    // TanStack Query re-envuelve el error axios; debe tener .response.status=409
    const err = caughtError as { response?: { status?: number } };
    expect(err.response?.status).toBe(409);
  });
});
