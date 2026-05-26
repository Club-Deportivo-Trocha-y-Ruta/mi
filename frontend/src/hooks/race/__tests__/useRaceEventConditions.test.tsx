/**
 * Tests para useUpdateRaceEventConditions (F-COND F4 — hook TanStack Query).
 *
 * Cubre:
 *  - Mutation llama updateRaceEventConditions(raceEventId, body).
 *  - Invalida queries con clave ["race-analysis"] y ["race-events", id]
 *    tras éxito.
 *  - Propaga errores del API sin throw silencioso.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/raceEvents", () => ({
  updateRaceEventConditions: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as api from "@/api/raceEvents";
import { useUpdateRaceEventConditions } from "../useRaceEventConditions";

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
  return { qc, wrapper };
}

const OK_RESPONSE = {
  race_event_id: 42,
  climate: "Soleado",
  temperature_c: "22.0",
  surface_condition: "seca" as const,
  altitude_msnm: 1000,
  weather_notes: null,
  updated_at: "2026-05-26T10:00:00Z",
};

beforeEach(() => vi.clearAllMocks());

describe("useUpdateRaceEventConditions", () => {
  it("llama updateRaceEventConditions(raceEventId, body) y resuelve con la response", async () => {
    vi.mocked(api.updateRaceEventConditions).mockResolvedValue(OK_RESPONSE);

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUpdateRaceEventConditions(), {
      wrapper,
    });

    await act(async () => {
      const r = await result.current.mutateAsync({
        raceEventId: 42,
        body: { surface_condition: "seca", temperature_c: 22 },
      });
      expect(r).toEqual(OK_RESPONSE);
    });

    expect(api.updateRaceEventConditions).toHaveBeenCalledWith(42, {
      surface_condition: "seca",
      temperature_c: 22,
    });
  });

  it("invalida ['race-analysis'] tras éxito", async () => {
    vi.mocked(api.updateRaceEventConditions).mockResolvedValue(OK_RESPONSE);

    const { qc, wrapper } = createWrapper();
    const spy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateRaceEventConditions(), {
      wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        raceEventId: 42,
        body: { climate: "Soleado" },
      });
    });

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ queryKey: ["race-analysis"] }),
    );
  });

  it("invalida ['race-events', raceEventId] tras éxito", async () => {
    vi.mocked(api.updateRaceEventConditions).mockResolvedValue(OK_RESPONSE);

    const { qc, wrapper } = createWrapper();
    const spy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateRaceEventConditions(), {
      wrapper,
    });

    await act(async () => {
      await result.current.mutateAsync({
        raceEventId: 99,
        body: { temperature_c: 18 },
      });
    });

    await waitFor(() =>
      expect(spy).toHaveBeenCalledWith({ queryKey: ["race-events", 99] }),
    );
  });

  it("propaga error sin throw silencioso", async () => {
    vi.mocked(api.updateRaceEventConditions).mockRejectedValue({
      response: { status: 422 },
    });

    const { wrapper } = createWrapper();
    const { result } = renderHook(() => useUpdateRaceEventConditions(), {
      wrapper,
    });

    await act(async () => {
      await expect(
        result.current.mutateAsync({
          raceEventId: 42,
          body: { temperature_c: 999 },
        }),
      ).rejects.toMatchObject({ response: { status: 422 } });
    });
  });

  it("NO invalida queries cuando la mutation falla", async () => {
    vi.mocked(api.updateRaceEventConditions).mockRejectedValue(new Error("x"));

    const { qc, wrapper } = createWrapper();
    const spy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useUpdateRaceEventConditions(), {
      wrapper,
    });

    await act(async () => {
      try {
        await result.current.mutateAsync({
          raceEventId: 1,
          body: { climate: "x" },
        });
      } catch {
        /* esperado */
      }
    });

    expect(spy).not.toHaveBeenCalled();
  });
});
