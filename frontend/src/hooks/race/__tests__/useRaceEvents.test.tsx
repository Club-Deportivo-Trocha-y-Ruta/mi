/**
 * Tests vitest para los hooks de race-events CRUD (CF3).
 *
 * Cubre:
 *  - useRaceEvent(id) consume getRaceEvent (endpoint detalle, no la lista filtrada)
 *  - useDeleteRaceEvent invalida la lista y el dropdown calendar
 *  - useRaceEventsList propaga filtros como query key
 *  - useUpdateRaceEvent invalida lista + detalle + calendar
 *  - getRaceEventErrorMessage mapea status codes a mensajes legibles
 *
 * Patron: mock de apiClient (no MSW) para verificar URLs/payloads explicitamente,
 * y QueryClient real para validar las invalidaciones por queryKey.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (sel: (s: { accessToken: string }) => unknown) =>
    sel({ accessToken: "test-token" }),
}));

import * as clientModule from "@/api/client";
import {
  getRaceEventErrorMessage,
  raceEventKeys,
  useDeleteRaceEvent,
  useRaceEvent,
  useRaceEventsList,
  useUpdateRaceEvent,
} from "@/hooks/race/useRaceEvents";

const { apiClient } = clientModule as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    patch: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

function wrapWithClient(client: QueryClient) {
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={client}>{children}</QueryClientProvider>
  );
}

function makeClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
}

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  apiClient.patch.mockReset();
  apiClient.delete.mockReset();
});

describe("useRaceEvent", () => {
  it("consume GET /race-events/:id (endpoint de detalle, no la lista)", async () => {
    apiClient.get.mockResolvedValueOnce({
      data: {
        id: 42,
        series_id: 1,
        sequence_number: 4,
        name: "Cali XCO",
        event_date: "2026-05-17",
        location: "Cali",
        is_championship: false,
        status: "completed",
        climate: null,
        temperature_c: null,
        surface_condition: null,
        altitude_msnm: null,
        weather_notes: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-05-17T18:00:00Z",
        created_by_user_id: 10,
      },
    });

    const client = makeClient();
    const { result } = renderHook(() => useRaceEvent(42), {
      wrapper: wrapWithClient(client),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiClient.get).toHaveBeenCalledTimes(1);
    // El path debe ser el GET /race-events/{id}, no el GET /race-events/ con filter
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/42",
      expect.objectContaining({ signal: expect.anything() }),
    );
    expect(result.current.data?.id).toBe(42);
  });

  it("queda deshabilitado cuando id es null", () => {
    const client = makeClient();
    const { result } = renderHook(() => useRaceEvent(null), {
      wrapper: wrapWithClient(client),
    });
    // No dispara request si id es null
    expect(apiClient.get).not.toHaveBeenCalled();
    expect(result.current.isFetching).toBe(false);
  });
});

describe("useRaceEventsList", () => {
  it("incluye los filtros en la query key (cache se segmenta por combinacion)", async () => {
    apiClient.get.mockResolvedValue({ data: { items: [], total: 0 } });
    const client = makeClient();
    const { result } = renderHook(
      () => useRaceEventsList({ season: 2026, status: "scheduled" }),
      { wrapper: wrapWithClient(client) },
    );
    await waitFor(() => expect(result.current.isSuccess).toBe(true));

    // La key debe incluir el objeto de filtros exactamente
    const cached = client.getQueryData(
      raceEventKeys.list({ season: 2026, status: "scheduled" }),
    );
    expect(cached).toEqual({ items: [], total: 0 });
  });
});

describe("useUpdateRaceEvent", () => {
  it("invalida lista, detalle y calendar-available al actualizar", async () => {
    apiClient.patch.mockResolvedValueOnce({
      data: { id: 7 },
    });
    const client = makeClient();
    const spy = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useUpdateRaceEvent(), {
      wrapper: wrapWithClient(client),
    });

    await result.current.mutateAsync({
      id: 7,
      body: { name: "Nuevo nombre" },
    });

    // 3 invalidaciones: lists, detail(7), calendar-available
    expect(spy).toHaveBeenCalledWith({ queryKey: raceEventKeys.lists() });
    expect(spy).toHaveBeenCalledWith({ queryKey: raceEventKeys.detail(7) });
    expect(spy).toHaveBeenCalledWith({
      queryKey: ["calendar", "race-events", "available-for-calendar"],
    });
  });
});

describe("useDeleteRaceEvent", () => {
  it("DELETE /race-events/:id e invalida lista y calendar-available", async () => {
    apiClient.delete.mockResolvedValueOnce({});
    const client = makeClient();
    const spy = vi.spyOn(client, "invalidateQueries");

    const { result } = renderHook(() => useDeleteRaceEvent(), {
      wrapper: wrapWithClient(client),
    });

    await result.current.mutateAsync({ id: 5 });

    expect(apiClient.delete).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/5",
      expect.objectContaining({ signal: undefined }),
    );
    // Invalidaciones requeridas (sin detalle: ya no existe el evento)
    expect(spy).toHaveBeenCalledWith({ queryKey: raceEventKeys.lists() });
    expect(spy).toHaveBeenCalledWith({
      queryKey: ["calendar", "race-events", "available-for-calendar"],
    });
  });

  it("propaga error 409 sin transformar (component muestra mensaje)", async () => {
    apiClient.delete.mockRejectedValueOnce({
      response: { status: 409, data: { detail: "Tiene dependencias" } },
    });
    const client = makeClient();
    const { result } = renderHook(() => useDeleteRaceEvent(), {
      wrapper: wrapWithClient(client),
    });

    await expect(result.current.mutateAsync({ id: 5 })).rejects.toMatchObject({
      response: { status: 409 },
    });
  });
});

describe("getRaceEventErrorMessage", () => {
  it("mapea 409 a mensaje de dependencias", () => {
    expect(getRaceEventErrorMessage({ response: { status: 409 } })).toMatch(
      /resultados importados o está vinculado al calendario/i,
    );
  });
  it("mapea 403 a 'sin permiso'", () => {
    expect(getRaceEventErrorMessage({ response: { status: 403 } })).toMatch(
      /sin permiso/i,
    );
  });
  it("mapea 404 a 'no encontrado'", () => {
    expect(getRaceEventErrorMessage({ response: { status: 404 } })).toMatch(
      /no encontrado/i,
    );
  });
  it("mapea 422 a 'datos inválidos'", () => {
    expect(getRaceEventErrorMessage({ response: { status: 422 } })).toMatch(
      /datos inválidos/i,
    );
  });
  it("usa el detail del backend cuando esta presente y no hay status match", () => {
    expect(
      getRaceEventErrorMessage({
        response: { data: { detail: "Mensaje custom del backend" } },
      }),
    ).toBe("Mensaje custom del backend");
  });
  it("usa fallback cuando el error no es interpretable", () => {
    expect(getRaceEventErrorMessage(null, "fallback")).toBe("fallback");
  });
});
