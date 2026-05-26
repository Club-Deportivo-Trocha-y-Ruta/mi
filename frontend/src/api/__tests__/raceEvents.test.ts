/**
 * Tests F-COND para api client de race-events.
 *
 * Verifica que `updateRaceEventConditions` llama al endpoint PATCH correcto
 * con el body y opciones esperadas (signal, etc).
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    patch: vi.fn(),
    delete: vi.fn(),
  },
}));

import * as clientModule from "@/api/client";
import { updateRaceEventConditions } from "@/api/raceEvents";

const { apiClient: mockApi } = clientModule as unknown as {
  apiClient: {
    patch: ReturnType<typeof vi.fn>;
  };
};

const OK_DATA = {
  race_event_id: 42,
  climate: "Soleado",
  temperature_c: "22",
  surface_condition: "seca" as const,
  altitude_msnm: 1000,
  weather_notes: null,
  updated_at: "2026-05-26T10:00:00Z",
};

beforeEach(() => {
  mockApi.patch.mockReset();
  mockApi.patch.mockResolvedValue({ data: OK_DATA });
});

describe("updateRaceEventConditions", () => {
  it("llama PATCH /api/race-analysis/race-events/{id}/conditions con el body", async () => {
    const body = {
      climate: "Lluvioso",
      temperature_c: 18,
      surface_condition: "barro" as const,
      altitude_msnm: 1340,
      weather_notes: "Pista lavada",
    };

    const r = await updateRaceEventConditions(42, body);

    expect(mockApi.patch).toHaveBeenCalledTimes(1);
    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/42/conditions",
      body,
      { signal: undefined },
    );
    expect(r).toEqual(OK_DATA);
  });

  it("propaga AbortSignal cuando se pasa en options", async () => {
    const controller = new AbortController();
    await updateRaceEventConditions(
      99,
      { surface_condition: "humeda" },
      { signal: controller.signal },
    );

    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/99/conditions",
      { surface_condition: "humeda" },
      { signal: controller.signal },
    );
  });

  it("acepta body parcial (PATCH semántico — solo un campo)", async () => {
    await updateRaceEventConditions(7, { temperature_c: 20 });

    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/7/conditions",
      { temperature_c: 20 },
      { signal: undefined },
    );
  });

  it("propaga errores del API sin transformarlos", async () => {
    mockApi.patch.mockRejectedValueOnce({ response: { status: 403 } });

    await expect(
      updateRaceEventConditions(42, { climate: "x" }),
    ).rejects.toMatchObject({ response: { status: 403 } });
  });

  it("acepta null explícito para limpiar un campo (PATCH unset)", async () => {
    await updateRaceEventConditions(42, {
      climate: null,
      weather_notes: null,
    });

    expect(mockApi.patch).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/42/conditions",
      { climate: null, weather_notes: null },
      { signal: undefined },
    );
  });
});
