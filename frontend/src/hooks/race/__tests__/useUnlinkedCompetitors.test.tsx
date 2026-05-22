/**
 * Tests para hooks de race-competitors (Option A R1).
 *
 * Verifica que cada hook invoca el endpoint correcto, propaga errores y
 * que el helper `getCompetitorErrorMessage` mapea status codes a copy es.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, act } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/raceCompetitors", () => ({
  listUnlinkedCompetitors: vi.fn(),
  getCompetitorSuggestions: vi.fn(),
  linkCompetitor: vi.fn(),
  unlinkCompetitor: vi.fn(),
}));

vi.mock("@/store/auth.store", () => ({
  useAuthStore: (selector: (s: { accessToken: string }) => unknown) =>
    selector({ accessToken: "test-token" }),
}));

import * as api from "@/api/raceCompetitors";

import {
  getCompetitorErrorMessage,
  useCompetitorSuggestions,
  useLinkCompetitor,
  useUnlinkCompetitor,
  useUnlinkedCompetitors,
} from "../useUnlinkedCompetitors";

function createWrapper() {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client: qc }, children);
}

beforeEach(() => vi.clearAllMocks());

describe("useUnlinkedCompetitors", () => {
  it("llama listUnlinkedCompetitors con filtros y devuelve items", async () => {
    vi.mocked(api.listUnlinkedCompetitors).mockResolvedValue({
      items: [
        {
          id: 1,
          display_name: "JUAN PEREZ",
          normalized_name: "juan perez",
          club_text: "Trocha y Ruta",
          sex: "M",
          results_count: 3,
          seasons: [2026],
          suggestions: [],
        },
      ],
      total: 1,
    });

    const { result } = renderHook(
      () => useUnlinkedCompetitors({ club_filter: "trocha", season: 2026 }),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.listUnlinkedCompetitors).toHaveBeenCalledWith({
      club_filter: "trocha",
      season: 2026,
    });
    expect(result.current.data?.items).toHaveLength(1);
  });
});

describe("useCompetitorSuggestions", () => {
  it("NO dispara fetch cuando enabled=false", async () => {
    const { result } = renderHook(
      () => useCompetitorSuggestions(5, false),
      { wrapper: createWrapper() },
    );
    // Espera un tick para confirmar que no se llamó
    await new Promise((r) => setTimeout(r, 50));
    expect(api.getCompetitorSuggestions).not.toHaveBeenCalled();
    expect(result.current.isFetching).toBe(false);
  });

  it("dispara fetch cuando enabled=true y competitorId está seteado", async () => {
    vi.mocked(api.getCompetitorSuggestions).mockResolvedValue({
      competitor_id: 5,
      suggestions: [
        { athlete_id: 1, full_name: "A", score: 0.9, reason: "x" },
      ],
    });

    const { result } = renderHook(
      () => useCompetitorSuggestions(5, true, 5),
      { wrapper: createWrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.getCompetitorSuggestions).toHaveBeenCalledWith(5, 5);
  });
});

describe("useLinkCompetitor", () => {
  it("llama linkCompetitor con competitorId y athleteId", async () => {
    vi.mocked(api.linkCompetitor).mockResolvedValue({
      competitor_id: 5,
      athlete_id: 12,
      linked_at: "2026-05-22T10:00:00Z",
      results_propagated: 4,
      already_linked: false,
    });

    const { result } = renderHook(() => useLinkCompetitor(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await result.current.mutateAsync({ competitorId: 5, athleteId: 12 });
    });
    expect(api.linkCompetitor).toHaveBeenCalledWith(5, 12);
  });

  it("propaga error 409 sin throw silencioso", async () => {
    vi.mocked(api.linkCompetitor).mockRejectedValue({
      response: { status: 409 },
    });

    const { result } = renderHook(() => useLinkCompetitor(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      await expect(
        result.current.mutateAsync({ competitorId: 1, athleteId: 2 }),
      ).rejects.toMatchObject({ response: { status: 409 } });
    });
  });
});

describe("useUnlinkCompetitor", () => {
  it("llama unlinkCompetitor y resuelve con was_linked=true", async () => {
    vi.mocked(api.unlinkCompetitor).mockResolvedValue({
      competitor_id: 7,
      was_linked: true,
      results_propagated: 2,
    });

    const { result } = renderHook(() => useUnlinkCompetitor(), {
      wrapper: createWrapper(),
    });

    await act(async () => {
      const r = await result.current.mutateAsync({ competitorId: 7 });
      expect(r.was_linked).toBe(true);
    });
    expect(api.unlinkCompetitor).toHaveBeenCalledWith(7);
  });
});

describe("getCompetitorErrorMessage", () => {
  it("mapea 409 → 'ya está enlazado'", () => {
    const msg = getCompetitorErrorMessage({
      response: { status: 409 },
    });
    expect(msg.toLowerCase()).toContain("ya está enlazado");
  });

  it("mapea 403 → 'sin permiso'", () => {
    const msg = getCompetitorErrorMessage({
      response: { status: 403 },
    });
    expect(msg.toLowerCase()).toContain("sin permiso");
  });

  it("mapea 404 → 'no encontrado'", () => {
    const msg = getCompetitorErrorMessage({
      response: { status: 404 },
    });
    expect(msg.toLowerCase()).toContain("no encontrado");
  });

  it("mapea 422 → 'datos inválidos'", () => {
    const msg = getCompetitorErrorMessage({
      response: { status: 422 },
    });
    expect(msg.toLowerCase()).toContain("datos inválidos");
  });

  it("usa fallback cuando el error es opaco", () => {
    const msg = getCompetitorErrorMessage(null, "Boom");
    expect(msg).toBe("Boom");
  });

  it("usa detail del backend cuando viene en string", () => {
    const msg = getCompetitorErrorMessage({
      response: { data: { detail: "Mensaje custom backend" }, status: 500 },
    });
    expect(msg).toBe("Mensaje custom backend");
  });
});
