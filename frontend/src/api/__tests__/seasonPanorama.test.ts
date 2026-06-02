/**
 * Tests del api client `getSeasonPanorama` (PR3 unificación /competitions).
 *
 * Verifica que llama al endpoint correcto y propaga `club_id` como query param.
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
import { getSeasonPanorama } from "@/api/athleteRaceAnalysis";
import type { SeasonPanoramaResponse } from "@/types/athleteRaceAnalysis.types";

const { apiClient: mockApi } = clientModule as unknown as {
  apiClient: { get: ReturnType<typeof vi.fn> };
};

const OK: SeasonPanoramaResponse = {
  season: 2026,
  total_athletes: 0,
  items: [],
};

beforeEach(() => {
  mockApi.get.mockReset();
  mockApi.get.mockResolvedValue({ data: OK });
});

describe("getSeasonPanorama", () => {
  it("GET /api/race-analysis/insights/season/{year} sin club_id", async () => {
    await getSeasonPanorama(2026);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/race-analysis/insights/season/2026",
      { params: {} },
    );
  });

  it("propaga club_id como query param cuando se pasa", async () => {
    await getSeasonPanorama(2026, 7);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/race-analysis/insights/season/2026",
      { params: { club_id: 7 } },
    );
  });

  it("retorna el data del response", async () => {
    const r = await getSeasonPanorama(2025);
    expect(r).toEqual(OK);
  });
});
