/**
 * Tests vitest — useAthleteRunOutcome (FR-013 / US1-Sc5).
 *
 * Verifica que el seguimiento del run lanzado notifique el desenlace:
 *  - done → toast de éxito, sin failureMessage.
 *  - failed/error/cancelled → toast de error + failureMessage.
 *  - running/hitl_waiting → sin toast, sin failureMessage (no terminal).
 *  - runId null / estado undefined → no-op (degradación con gracia).
 *  - no re-emite el toast en re-renders del mismo estado terminal.
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook } from "@testing-library/react";

import type { RunState } from "@/types/raceAnalysis.types";

// --- Mocks ------------------------------------------------------------------

const toastSuccess = vi.fn();
const toastError = vi.fn();
vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args),
    error: (...args: unknown[]) => toastError(...args),
  },
}));

const invalidateQueries = vi.fn();
vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries }),
}));

let mockRunState: RunState | undefined;
vi.mock("@/hooks/ai/useRaceRun", async () => {
  const actual = await vi.importActual<typeof import("@/hooks/ai/useRaceRun")>(
    "@/hooks/ai/useRaceRun",
  );
  return {
    ...actual,
    useRunStatus: () => ({
      data: mockRunState
        ? { latest: { state: mockRunState }, events: [] }
        : undefined,
    }),
  };
});

import { useAthleteRunOutcome } from "@/hooks/ai/useAthleteRunOutcome";

const OPTS = { athleteId: 55, displayName: "Ana Ficticia" };

beforeEach(() => {
  vi.clearAllMocks();
  mockRunState = undefined;
});

describe("useAthleteRunOutcome", () => {
  it("done → toast de éxito + invalida insights, sin failureMessage", () => {
    mockRunState = "done";
    const { result } = renderHook(() => useAthleteRunOutcome("run-1", OPTS));

    expect(toastSuccess).toHaveBeenCalledTimes(1);
    expect(toastSuccess).toHaveBeenCalledWith(
      "Análisis de Ana Ficticia completado.",
    );
    expect(invalidateQueries).toHaveBeenCalledTimes(1);
    expect(toastError).not.toHaveBeenCalled();
    expect(result.current.failureMessage).toBeNull();
  });

  it.each<RunState>(["failed", "error"])(
    "%s → toast de error + failureMessage",
    (state) => {
      mockRunState = state;
      const { result } = renderHook(() => useAthleteRunOutcome("run-2", OPTS));

      expect(toastError).toHaveBeenCalledTimes(1);
      expect(result.current.failureMessage).toBe(
        "El análisis de Ana Ficticia falló. Intenta de nuevo.",
      );
      expect(toastSuccess).not.toHaveBeenCalled();
      expect(invalidateQueries).not.toHaveBeenCalled();
    },
  );

  it("cancelled → mensaje de cancelación", () => {
    mockRunState = "cancelled";
    const { result } = renderHook(() => useAthleteRunOutcome("run-3", OPTS));

    expect(toastError).toHaveBeenCalledTimes(1);
    expect(result.current.failureMessage).toBe(
      "El análisis de Ana Ficticia fue cancelado.",
    );
  });

  it.each<RunState>(["running", "hitl_waiting"])(
    "%s (no terminal) → sin toast ni failureMessage",
    (state) => {
      mockRunState = state;
      const { result } = renderHook(() => useAthleteRunOutcome("run-4", OPTS));

      expect(toastSuccess).not.toHaveBeenCalled();
      expect(toastError).not.toHaveBeenCalled();
      expect(result.current.failureMessage).toBeNull();
    },
  );

  it("runId null → no-op aunque el estado sea terminal", () => {
    mockRunState = "done";
    const { result } = renderHook(() => useAthleteRunOutcome(null, OPTS));

    expect(toastSuccess).not.toHaveBeenCalled();
    expect(result.current.failureMessage).toBeNull();
  });

  it("no re-emite el toast en re-renders del mismo run terminal", () => {
    mockRunState = "done";
    const { rerender } = renderHook(() => useAthleteRunOutcome("run-5", OPTS));
    rerender();
    rerender();

    expect(toastSuccess).toHaveBeenCalledTimes(1);
  });
});
