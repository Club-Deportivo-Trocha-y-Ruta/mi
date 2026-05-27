/**
 * Tests CRUD (CF3) para api/raceEvents — createRaceEvent, updateRaceEvent,
 * deleteRaceEvent, getRaceEvent, listRaceEvents.
 *
 * Se separa de raceEvents.test.ts (que cubre F-COND) para mantener archivos
 * por contrato/endpoint y evitar mezclar mocks.
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
import {
  createRaceEvent,
  deleteRaceEvent,
  getRaceEvent,
  listRaceEvents,
  updateRaceEvent,
} from "@/api/raceEvents";

const { apiClient } = clientModule as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    patch: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

beforeEach(() => {
  apiClient.get.mockReset();
  apiClient.post.mockReset();
  apiClient.patch.mockReset();
  apiClient.delete.mockReset();
});

describe("createRaceEvent", () => {
  it("POST /api/race-analysis/race-events/ con el body", async () => {
    apiClient.post.mockResolvedValueOnce({ data: { id: 1 } });
    const body = {
      series_id: 1,
      sequence_number: 4,
      name: "Cali XCO",
      event_date: "2026-05-17",
      location: "Cali",
      is_championship: false,
      status: "scheduled" as const,
    };
    const result = await createRaceEvent(body);
    expect(apiClient.post).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/",
      body,
      { signal: undefined },
    );
    expect(result).toEqual({ id: 1 });
  });
});

describe("updateRaceEvent", () => {
  it("PATCH /api/race-analysis/race-events/:id con el body", async () => {
    apiClient.patch.mockResolvedValueOnce({ data: { id: 7 } });
    const body = { name: "Nuevo" };
    const result = await updateRaceEvent(7, body);
    expect(apiClient.patch).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/7",
      body,
      { signal: undefined },
    );
    expect(result).toEqual({ id: 7 });
  });
});

describe("deleteRaceEvent", () => {
  it("DELETE /api/race-analysis/race-events/:id", async () => {
    apiClient.delete.mockResolvedValueOnce({});
    await deleteRaceEvent(3);
    expect(apiClient.delete).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/3",
      { signal: undefined },
    );
  });
});

describe("getRaceEvent", () => {
  it("GET /api/race-analysis/race-events/:id", async () => {
    apiClient.get.mockResolvedValueOnce({ data: { id: 9, name: "X" } });
    const r = await getRaceEvent(9);
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/9",
      { signal: undefined },
    );
    expect(r.id).toBe(9);
  });
});

describe("listRaceEvents", () => {
  it("GET /api/race-analysis/race-events/ con params como query string", async () => {
    apiClient.get.mockResolvedValueOnce({ data: { items: [], total: 0 } });
    const filters = { season: 2026, status: "scheduled" as const };
    await listRaceEvents(filters);
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/",
      { params: filters, signal: undefined },
    );
  });

  it("acepta filtros vacios (sin params)", async () => {
    apiClient.get.mockResolvedValueOnce({ data: { items: [], total: 0 } });
    await listRaceEvents();
    expect(apiClient.get).toHaveBeenCalledWith(
      "/api/race-analysis/race-events/",
      { params: {}, signal: undefined },
    );
  });
});
