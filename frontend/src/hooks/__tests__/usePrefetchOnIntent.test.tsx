import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import {
  usePrefetchOnIntent,
  __resetPrefetchOnIntentForTests,
} from "@/hooks/usePrefetchOnIntent";

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

function makeClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: Infinity } },
  });
}

describe("usePrefetchOnIntent (feature 012, US3)", () => {
  beforeEach(() => __resetPrefetchOnIntentForTests());
  afterEach(() => {
    vi.clearAllMocks();
    __resetPrefetchOnIntentForTests();
  });

  it("prefetches the query into the cache on intent", async () => {
    const qc = makeClient();
    const queryFn = vi.fn().mockResolvedValue({ id: 7, name: "Valida" });
    const { result } = renderHook(() => usePrefetchOnIntent(), {
      wrapper: wrapper(qc),
    });

    result.current({ queryKey: ["raceEvents", "detail", 7], queryFn });

    await waitFor(() =>
      expect(qc.getQueryData(["raceEvents", "detail", 7])).toEqual({
        id: 7,
        name: "Valida",
      }),
    );
    expect(queryFn).toHaveBeenCalledTimes(1);
  });

  it("dedupes: repeated intent on the same key fetches only once", async () => {
    const qc = makeClient();
    const queryFn = vi.fn().mockResolvedValue("data");
    const { result } = renderHook(() => usePrefetchOnIntent(), {
      wrapper: wrapper(qc),
    });

    result.current({ queryKey: ["raceEvents", "detail", 7], queryFn });
    result.current({ queryKey: ["raceEvents", "detail", 7], queryFn });
    result.current({ queryKey: ["raceEvents", "detail", 7], queryFn });

    await waitFor(() =>
      expect(qc.getQueryData(["raceEvents", "detail", 7])).toBe("data"),
    );
    expect(queryFn).toHaveBeenCalledTimes(1);
  });

  it("does NOT refetch data that is already fresh in the cache", async () => {
    const qc = makeClient();
    qc.setQueryData(["raceEvents", "detail", 9], { id: 9 });
    const queryFn = vi.fn().mockResolvedValue({ id: 9, fresh: true });
    const { result } = renderHook(() => usePrefetchOnIntent(), {
      wrapper: wrapper(qc),
    });

    result.current({
      queryKey: ["raceEvents", "detail", 9],
      queryFn,
      staleTime: 5 * 60_000,
    });

    // prefetchQuery respects staleTime: data just set is fresh → no fetch.
    await new Promise((r) => setTimeout(r, 20));
    expect(queryFn).not.toHaveBeenCalled();
  });

  it("prefetches distinct keys independently", async () => {
    const qc = makeClient();
    const queryFn = vi.fn().mockResolvedValue("x");
    const { result } = renderHook(() => usePrefetchOnIntent(), {
      wrapper: wrapper(qc),
    });

    result.current({ queryKey: ["raceEvents", "detail", 1], queryFn });
    result.current({ queryKey: ["raceEvents", "detail", 2], queryFn });

    await waitFor(() => expect(queryFn).toHaveBeenCalledTimes(2));
  });
});
