/**
 * Tests del api client PR4: catálogo de motivos + diff read-only.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => ({
  apiClient: { get: vi.fn(), post: vi.fn() },
}));

import * as clientModule from "@/api/client";
import { getRevisionReasons, getRaceEventDiff } from "@/api/raceImports";

const { apiClient: mockApi } = clientModule as unknown as {
  apiClient: { get: ReturnType<typeof vi.fn> };
};

beforeEach(() => {
  mockApi.get.mockReset();
});

describe("getRevisionReasons", () => {
  it("GET /api/race-analysis/imports/revision-reasons", async () => {
    mockApi.get.mockResolvedValue({ data: { options: [] } });
    await getRevisionReasons();
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/race-analysis/imports/revision-reasons",
      { signal: undefined },
    );
  });
});

describe("getRaceEventDiff", () => {
  it("GET /api/race-analysis/imports/{id}/diff", async () => {
    mockApi.get.mockResolvedValue({
      data: { race_event_id: 5, has_revision: false, counts: {}, items: [] },
    });
    const r = await getRaceEventDiff(5);
    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/race-analysis/imports/5/diff",
      { signal: undefined },
    );
    expect(r.race_event_id).toBe(5);
  });
});
