import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement } from "react";

vi.mock("@/api/athleteRaceAnalysis", async () => {
  const actual = await vi.importActual<typeof import("@/api/athleteRaceAnalysis")>(
    "@/api/athleteRaceAnalysis",
  );
  return { ...actual, answerInsight: vi.fn() };
});

import { useAnswerInsight } from "./useAnswerInsight";
import * as api from "@/api/athleteRaceAnalysis";
import { mockInsightV3Detail } from "@/test/fixtures/insightV3";
import type { AthleteInsightDetailOut } from "@/types/athleteRaceAnalysis.types";

const ATHLETE_ID = 42;
const INSIGHT_ID = 2001;

function createWrapper(queryClient: QueryClient) {
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

function newClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
}

describe("useAnswerInsight", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("envía answer_text y rating, y actualiza la cache de detalle en éxito", async () => {
    const queryClient = newClient();
    const detailKey = ["athlete-insight-detail", ATHLETE_ID, INSIGHT_ID];
    const initial = mockInsightV3Detail({ id: INSIGHT_ID });
    queryClient.setQueryData(detailKey, initial);

    const serverResponse: AthleteInsightDetailOut = {
      ...initial,
      coach_answer_text: "Se sintió cómodo en el tramo técnico.",
      coach_answer_at: "2026-06-01T10:00:00Z",
      coach_rating: 1,
    };
    vi.mocked(api.answerInsight).mockResolvedValue(serverResponse);

    const { result } = renderHook(() => useAnswerInsight(ATHLETE_ID), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      await result.current.mutateAsync({
        insightId: INSIGHT_ID,
        body: { answer_text: "Se sintió cómodo en el tramo técnico.", rating: 1 },
      });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.answerInsight).toHaveBeenCalledWith(ATHLETE_ID, INSIGHT_ID, {
      answer_text: "Se sintió cómodo en el tramo técnico.",
      rating: 1,
    });

    const cached = queryClient.getQueryData<AthleteInsightDetailOut>(detailKey);
    expect(cached?.coach_answer_text).toBe("Se sintió cómodo en el tramo técnico.");
    expect(cached?.coach_rating).toBe(1);
  });

  it("aplica una actualización optimista de coach_rating antes de que resuelva la mutación", async () => {
    const queryClient = newClient();
    const detailKey = ["athlete-insight-detail", ATHLETE_ID, INSIGHT_ID];
    const initial = mockInsightV3Detail({ id: INSIGHT_ID, coach_rating: null });
    queryClient.setQueryData(detailKey, initial);

    let resolveFn: (value: AthleteInsightDetailOut) => void = () => {};
    vi.mocked(api.answerInsight).mockReturnValue(
      new Promise((resolve) => {
        resolveFn = resolve;
      }),
    );

    const { result } = renderHook(() => useAnswerInsight(ATHLETE_ID), {
      wrapper: createWrapper(queryClient),
    });

    act(() => {
      result.current.mutate({ insightId: INSIGHT_ID, body: { rating: -1 } });
    });

    await waitFor(() => {
      const cached = queryClient.getQueryData<AthleteInsightDetailOut>(detailKey);
      expect(cached?.coach_rating).toBe(-1);
    });

    resolveFn({ ...initial, coach_rating: -1 });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
  });

  it("revierte la actualización optimista si la mutación falla", async () => {
    const queryClient = newClient();
    const detailKey = ["athlete-insight-detail", ATHLETE_ID, INSIGHT_ID];
    const initial = mockInsightV3Detail({ id: INSIGHT_ID, coach_rating: null });
    queryClient.setQueryData(detailKey, initial);

    vi.mocked(api.answerInsight).mockRejectedValue(new Error("network error"));

    const { result } = renderHook(() => useAnswerInsight(ATHLETE_ID), {
      wrapper: createWrapper(queryClient),
    });

    await act(async () => {
      try {
        await result.current.mutateAsync({ insightId: INSIGHT_ID, body: { rating: 1 } });
      } catch {
        // esperado
      }
    });

    await waitFor(() => expect(result.current.isError).toBe(true));
    const cached = queryClient.getQueryData<AthleteInsightDetailOut>(detailKey);
    expect(cached?.coach_rating).toBeNull();
  });
});
