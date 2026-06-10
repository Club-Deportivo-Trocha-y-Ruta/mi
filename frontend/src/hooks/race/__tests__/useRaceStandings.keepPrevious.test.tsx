import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

vi.mock("@/api/raceStandings", () => ({ getRaceStandings: vi.fn() }));
vi.mock("@/store/auth.store", () => ({ useAuthStore: vi.fn() }));

import { getRaceStandings } from "@/api/raceStandings";
import { useAuthStore } from "@/store/auth.store";
import { useRaceStandings } from "@/hooks/race/useRaceStandings";

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

const standingsA = { season: 2026, rows: [{ display_name: "A" }] };
const standingsB = { season: 2026, rows: [{ display_name: "B" }] };

describe("useRaceStandings — keepPreviousData (feature 012, US3)", () => {
  afterEach(() => vi.clearAllMocks());

  it("keeps the previous standings visible while the next event loads", async () => {
    vi.mocked(useAuthStore).mockImplementation((sel: unknown) =>
      (sel as (s: { accessToken: string }) => unknown)({ accessToken: "tok" }),
    );

    const qc = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });

    // First event resolves immediately.
    vi.mocked(getRaceStandings).mockResolvedValueOnce(standingsA as never);

    const { result, rerender } = renderHook(({ id }) => useRaceStandings(id), {
      wrapper: wrapper(qc),
      initialProps: { id: 1 as number },
    });

    await waitFor(() => expect(result.current.data).toEqual(standingsA));

    // Second event hangs — we should keep showing standingsA meanwhile.
    let resolveB!: (v: unknown) => void;
    vi.mocked(getRaceStandings).mockReturnValueOnce(
      new Promise((r) => {
        resolveB = r;
      }) as never,
    );

    rerender({ id: 2 });

    // Previous data stays on screen (no empty flash) and is flagged as placeholder.
    await waitFor(() => expect(result.current.isPlaceholderData).toBe(true));
    expect(result.current.data).toEqual(standingsA);

    resolveB(standingsB);
    await waitFor(() => expect(result.current.data).toEqual(standingsB));
  });
});
