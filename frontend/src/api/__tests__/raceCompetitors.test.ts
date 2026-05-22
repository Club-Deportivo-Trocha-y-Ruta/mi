/**
 * Tests para API client de race-competitors (Option A R1).
 *
 * Verifica que cada función llama al endpoint correcto con los params
 * esperados y devuelve la data del response.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";

vi.mock("@/api/client", () => ({
  apiClient: {
    get: vi.fn(),
    post: vi.fn(),
    delete: vi.fn(),
  },
}));

import * as clientModule from "@/api/client";
import {
  getCompetitorSuggestions,
  linkCompetitor,
  listUnlinkedCompetitors,
  unlinkCompetitor,
} from "@/api/raceCompetitors";

const { apiClient: mockApi } = clientModule as unknown as {
  apiClient: {
    get: ReturnType<typeof vi.fn>;
    post: ReturnType<typeof vi.fn>;
    delete: ReturnType<typeof vi.fn>;
  };
};

beforeEach(() => {
  mockApi.get.mockReset();
  mockApi.post.mockReset();
  mockApi.delete.mockReset();
});

describe("listUnlinkedCompetitors", () => {
  it("aplica defaults documentados y devuelve items", async () => {
    mockApi.get.mockResolvedValue({
      data: {
        items: [
          {
            id: 1,
            display_name: "JUAN PEREZ",
            normalized_name: "juan perez",
            club_text: "Trocha y Ruta",
            sex: "M",
            results_count: 3,
            seasons: [2025, 2026],
            suggestions: [],
          },
        ],
        total: 1,
      },
    });

    const result = await listUnlinkedCompetitors();

    expect(mockApi.get).toHaveBeenCalledWith("/api/race-competitors/", {
      params: {
        unlinked: true,
        club_filter: undefined,
        season: undefined,
        include_suggestions: true,
        suggestions_limit: 3,
        limit: 50,
        offset: 0,
      },
      signal: undefined,
    });
    expect(result.items).toHaveLength(1);
    expect(result.total).toBe(1);
  });

  it("propaga filtros de club y temporada", async () => {
    mockApi.get.mockResolvedValue({ data: { items: [], total: 0 } });

    await listUnlinkedCompetitors({
      club_filter: "trocha",
      season: 2026,
      limit: 100,
      offset: 50,
    });

    const call = mockApi.get.mock.calls[0];
    expect(call[1].params).toMatchObject({
      club_filter: "trocha",
      season: 2026,
      limit: 100,
      offset: 50,
      unlinked: true,
    });
  });
});

describe("getCompetitorSuggestions", () => {
  it("llama GET con limit explícito", async () => {
    mockApi.get.mockResolvedValue({
      data: {
        competitor_id: 42,
        suggestions: [
          {
            athlete_id: 7,
            full_name: "Tomás García",
            score: 0.93,
            reason: "Match exacto",
          },
        ],
      },
    });

    const r = await getCompetitorSuggestions(42, 10);

    expect(mockApi.get).toHaveBeenCalledWith(
      "/api/race-competitors/42/suggestions",
      { params: { limit: 10 }, signal: undefined },
    );
    expect(r.suggestions[0].score).toBe(0.93);
  });

  it("usa limit default = 5", async () => {
    mockApi.get.mockResolvedValue({
      data: { competitor_id: 1, suggestions: [] },
    });
    await getCompetitorSuggestions(1);
    expect(mockApi.get.mock.calls[0][1].params.limit).toBe(5);
  });
});

describe("linkCompetitor", () => {
  it("envía body con athlete_id y devuelve metadata", async () => {
    mockApi.post.mockResolvedValue({
      data: {
        competitor_id: 5,
        athlete_id: 12,
        linked_at: "2026-05-22T10:00:00Z",
        results_propagated: 4,
        already_linked: false,
      },
    });

    const r = await linkCompetitor(5, 12);

    expect(mockApi.post).toHaveBeenCalledWith(
      "/api/race-competitors/5/link",
      { athlete_id: 12 },
      { signal: undefined },
    );
    expect(r.results_propagated).toBe(4);
    expect(r.already_linked).toBe(false);
  });

  it("propaga errores axios (ej. 409)", async () => {
    mockApi.post.mockRejectedValue({
      response: { status: 409, data: { detail: "Already linked" } },
    });
    await expect(linkCompetitor(1, 2)).rejects.toMatchObject({
      response: { status: 409 },
    });
  });
});

describe("unlinkCompetitor", () => {
  it("envía DELETE en la ruta correcta", async () => {
    mockApi.delete.mockResolvedValue({
      data: {
        competitor_id: 7,
        was_linked: true,
        results_propagated: 2,
      },
    });

    const r = await unlinkCompetitor(7);

    expect(mockApi.delete).toHaveBeenCalledWith(
      "/api/race-competitors/7/link",
      { signal: undefined },
    );
    expect(r.was_linked).toBe(true);
  });
});
