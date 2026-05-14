import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

// ─── Mocks ───────────────────────────────────────────────────────────────────

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
    interceptors: {
      request: { use: vi.fn() },
      response: { use: vi.fn() },
    },
  },
  registerAuthHandlers: vi.fn(),
}));

import * as apiClientModule from "@/api/client";
import {
  useCalendarEvents,
  useCalendarEvent,
  useCreateCalendarEvent,
  useCancelCalendarEvent,
  fetchCalendarEvents,
  fetchCalendarEvent,
  createCalendarEvent,
  updateCalendarEvent,
  cancelCalendarEvent,
} from "./calendar";
import { makeCalendarListItem, makeCalendarEventRead } from "@/test/msw/calendarHandlers";
import type { CalendarFilters, EventCreatePayload, EventUpdatePayload } from "@/types/calendar.types";

const { apiClient: mockApi } = apiClientModule as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    patch: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

// ─── API function tests ───────────────────────────────────────────────────────

describe("fetchCalendarEvents", () => {
  beforeEach(() => mockApi.get.mockClear());

  it("calls GET /api/calendar/events with correct params", async () => {
    const items = [makeCalendarListItem()];
    mockApi.get.mockResolvedValue({ data: items });

    const filters: CalendarFilters = { from: "2026-05-01", to: "2026-05-31" };
    const result = await fetchCalendarEvents(filters);

    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/calendar/events",
      expect.objectContaining({ params: expect.objectContaining({ from: "2026-05-01", to: "2026-05-31" }) }),
    );
    expect(result).toEqual(items);
  });

  it("includes event_types in params when provided", async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    const filters: CalendarFilters = {
      from: "2026-05-01",
      to: "2026-05-31",
      event_types: ["competition", "club_event"],
    };
    await fetchCalendarEvents(filters);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/calendar/events",
      expect.objectContaining({
        params: expect.objectContaining({ "event_types[]": ["competition", "club_event"] }),
      }),
    );
  });
});

describe("fetchCalendarEvent", () => {
  it("calls GET /api/calendar/events/:id", async () => {
    const ev = makeCalendarEventRead({ id: 5 });
    mockApi.get.mockResolvedValue({ data: ev });
    const result = await fetchCalendarEvent(5);
    expect(mockApi.get).toHaveBeenCalledWith("/api/calendar/events/5");
    expect(result.id).toBe(5);
  });
});

describe("createCalendarEvent", () => {
  it("calls POST /api/calendar/events", async () => {
    const created = makeCalendarEventRead({ id: 99 });
    mockApi.post.mockResolvedValue({ data: created });

    const payload: EventCreatePayload = {
      event_type: "club_event",
      title: "Asamblea anual",
      start_at: "2026-06-01T18:00:00",
      end_at: "2026-06-01T20:00:00",
      audiences: [{ audience_type: "all_club", audience_value: {} as Record<string, never> }],
    };
    const result = await createCalendarEvent(payload);
    expect(mockApi.post).toHaveBeenCalledWith("/api/calendar/events", payload);
    expect(result.id).toBe(99);
  });
});

describe("updateCalendarEvent", () => {
  it("calls PATCH /api/calendar/events/:id", async () => {
    const updated = makeCalendarEventRead({ id: 3, title: "Nuevo título" });
    mockApi.patch.mockResolvedValue({ data: updated });
    const payload: EventUpdatePayload = { title: "Nuevo título" };
    const result = await updateCalendarEvent(3, payload);
    expect(mockApi.patch).toHaveBeenCalledWith("/api/calendar/events/3", payload);
    expect(result.title).toBe("Nuevo título");
  });
});

describe("cancelCalendarEvent", () => {
  it("calls DELETE /api/calendar/events/:id", async () => {
    const cancelled = makeCalendarEventRead({ id: 1, status: "cancelled" });
    mockApi.delete.mockResolvedValue({ data: cancelled });
    const result = await cancelCalendarEvent(1, "prueba");
    expect(mockApi.delete).toHaveBeenCalledWith(
      "/api/calendar/events/1",
      expect.objectContaining({ params: { reason: "prueba" } }),
    );
    expect(result.status).toBe("cancelled");
  });
});

// ─── TanStack Query hook tests ────────────────────────────────────────────────

describe("useCalendarEvents", () => {
  beforeEach(() => mockApi.get.mockClear());

  it("fetches events and returns data", async () => {
    const items = [makeCalendarListItem(), makeCalendarListItem({ id: 2 })];
    mockApi.get.mockResolvedValue({ data: items });

    const wrapper = createWrapper();
    const filters: CalendarFilters = { from: "2026-05-01", to: "2026-05-31" };
    const { result } = renderHook(() => useCalendarEvents(filters), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(2);
  });

  it("uses correct query key", async () => {
    mockApi.get.mockResolvedValue({ data: [] });
    const wrapper = createWrapper();
    const filters: CalendarFilters = { from: "2026-05-01", to: "2026-05-31" };
    const { result } = renderHook(() => useCalendarEvents(filters), { wrapper });
    await waitFor(() => expect(result.current.isFetching).toBe(false));
    // Query key includes "calendar", "events" and filters
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/calendar/events",
      expect.any(Object),
    );
  });
});

describe("useCalendarEvent", () => {
  it("is disabled when id is null", () => {
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCalendarEvent(null), { wrapper });
    expect(result.current.fetchStatus).toBe("idle");
  });

  it("fetches event when id is provided", async () => {
    const ev = makeCalendarEventRead({ id: 7 });
    mockApi.get.mockResolvedValue({ data: ev });
    const wrapper = createWrapper();
    const { result } = renderHook(() => useCalendarEvent(7), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.id).toBe(7);
  });
});

describe("useCreateCalendarEvent", () => {
  it("invalidates calendar events query on success", async () => {
    const created = makeCalendarEventRead({ id: 50 });
    mockApi.post.mockResolvedValue({ data: created });
    mockApi.get.mockResolvedValue({ data: [] });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(() => useCreateCalendarEvent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({
        event_type: "club_event",
        title: "Test",
        start_at: "2026-06-01T18:00:00",
        end_at: "2026-06-01T20:00:00",
        audiences: [{ audience_type: "all_club", audience_value: {} as Record<string, never> }],
      });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["calendar", "events"] }),
    );
  });
});

describe("useCancelCalendarEvent", () => {
  it("invalidates event detail and list on success", async () => {
    const cancelled = makeCalendarEventRead({ id: 2, status: "cancelled" });
    mockApi.delete.mockResolvedValue({ data: cancelled });
    mockApi.get.mockResolvedValue({ data: [] });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false, gcTime: 0 }, mutations: { retry: false } },
    });
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries");
    const wrapper = ({ children }: { children: React.ReactNode }) =>
      createElement(QueryClientProvider, { client: queryClient }, children);

    const { result } = renderHook(() => useCancelCalendarEvent(), { wrapper });

    await act(async () => {
      await result.current.mutateAsync({ id: 2 });
    });

    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["calendar", "events"] }),
    );
    expect(invalidateSpy).toHaveBeenCalledWith(
      expect.objectContaining({ queryKey: ["calendar", "event", 2] }),
    );
  });
});
