import { afterEach, describe, expect, it, vi } from "vitest";
import type { ReactNode } from "react";
import { act, renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

import { rosterKeys, useUpdateRosterEntry } from "@/hooks/race/useRaceRoster";
import type { RaceRosterResponse } from "@/types/raceRoster.types";

vi.mock("@/api/raceRoster", () => ({
  updateRosterEntry: vi.fn(),
  createRosterEntry: vi.fn(),
  deleteRosterEntry: vi.fn(),
  getRaceRoster: vi.fn(),
}));

import { updateRosterEntry } from "@/api/raceRoster";

const RACE = 5;
const ENTRY = 11;

function seedRoster(): RaceRosterResponse {
  return {
    race_event_id: RACE,
    entries: [
      { id: 11, athlete_id: 1, athlete_name: "A", status: "called_up", note: null },
      { id: 12, athlete_id: 2, athlete_name: "B", status: "called_up", note: null },
    ],
    reconciliation: { called_up_no_result: [], result_not_called_up: [] },
  };
}

function makeClient() {
  // gcTime Infinity: keep the seeded roster query alive without an active
  // observer (gcTime 0 would collect it before onMutate reads it).
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity },
      mutations: { retry: false },
    },
  });
}

function wrapper(qc: QueryClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
  };
}

describe("useUpdateRosterEntry — optimistic (feature 012, US3)", () => {
  afterEach(() => vi.clearAllMocks());

  it("updates the cached roster entry immediately on mutate", async () => {
    const qc = makeClient();
    qc.setQueryData(rosterKeys.byEvent(RACE), seedRoster());

    // Server hangs so we can observe the optimistic state.
    let resolveServer!: (v: unknown) => void;
    vi.mocked(updateRosterEntry).mockReturnValue(
      new Promise((r) => {
        resolveServer = r;
      }) as never,
    );

    const { result } = renderHook(() => useUpdateRosterEntry(), {
      wrapper: wrapper(qc),
    });

    act(() => {
      result.current.mutate({
        raceEventId: RACE,
        entryId: ENTRY,
        body: { status: "confirmed" },
      });
    });

    await waitFor(() => {
      const data = qc.getQueryData<RaceRosterResponse>(rosterKeys.byEvent(RACE));
      expect(data?.entries.find((e) => e.id === ENTRY)?.status).toBe("confirmed");
    });
    // Other entries untouched.
    const data = qc.getQueryData<RaceRosterResponse>(rosterKeys.byEvent(RACE));
    expect(data?.entries.find((e) => e.id === 12)?.status).toBe("called_up");

    resolveServer({
      id: ENTRY,
      athlete_id: 1,
      athlete_name: "A",
      status: "confirmed",
      note: null,
    });
  });

  it("rolls the change back when the server rejects it", async () => {
    const qc = makeClient();
    qc.setQueryData(rosterKeys.byEvent(RACE), seedRoster());
    vi.mocked(updateRosterEntry).mockRejectedValue(new Error("conflict"));

    const { result } = renderHook(() => useUpdateRosterEntry(), {
      wrapper: wrapper(qc),
    });

    act(() => {
      result.current.mutate({
        raceEventId: RACE,
        entryId: ENTRY,
        body: { status: "withdrawn" },
      });
    });

    await waitFor(() => expect(result.current.isError).toBe(true));

    const data = qc.getQueryData<RaceRosterResponse>(rosterKeys.byEvent(RACE));
    // Rolled back to the original status.
    expect(data?.entries.find((e) => e.id === ENTRY)?.status).toBe("called_up");
  });
});
