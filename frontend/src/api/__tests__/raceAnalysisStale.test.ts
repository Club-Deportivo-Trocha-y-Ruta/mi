/**
 * Tests del api client PR5: invalidate + re-execute.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => ({
  apiClient: { post: vi.fn(), get: vi.fn() },
}));

import * as clientModule from "@/api/client";
import { invalidateRun, reExecuteRun } from "@/api/raceAnalysis";

const { apiClient: mockApi } = clientModule as unknown as {
  apiClient: { post: ReturnType<typeof vi.fn> };
};

beforeEach(() => {
  mockApi.post.mockReset();
});

describe("invalidateRun", () => {
  it("POST /api/race-analysis/runs/:id/invalidate", async () => {
    mockApi.post.mockResolvedValue({ data: { run_id: "abc", stale: true } });
    const r = await invalidateRun("abc");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/race-analysis/runs/abc/invalidate",
      undefined,
      { signal: undefined },
    );
    expect(r.stale).toBe(true);
  });
});

describe("reExecuteRun", () => {
  it("POST /api/race-analysis/runs/:id/re-execute", async () => {
    mockApi.post.mockResolvedValue({
      data: {
        run_id: "new-run",
        status: "running",
        started_at: "2026-06-01T10:00:00Z",
        status_url: "/x",
        estimated_seconds: 20,
      },
    });
    const r = await reExecuteRun("abc");
    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/race-analysis/runs/abc/re-execute",
      undefined,
      { signal: undefined },
    );
    expect(r.run_id).toBe("new-run");
  });
});
