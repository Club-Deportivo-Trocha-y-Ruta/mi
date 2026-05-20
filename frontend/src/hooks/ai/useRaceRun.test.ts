/**
 * Tests para los hooks race-analysis v2 (F6.1-6.3).
 *
 * - useStartRun: dispara POST y devuelve run_id.
 * - useRunStatus: polling, acumula eventos, se detiene en terminal.
 * - useApproveStep: POST con decision.
 *
 * Mockea `@/api/raceAnalysis` con vi.mock para evitar requests reales.
 */
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, act } from "@testing-library/react";
import { createElement } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  getRunResult: vi.fn(),
}));

import * as raceApi from "@/api/raceAnalysis";

import {
  isTerminalState,
  useApproveStep,
  useRunStatus,
  useStartRun,
} from "./useRaceRun";

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return ({ children }: { children: React.ReactNode }) =>
    createElement(QueryClientProvider, { client: queryClient }, children);
}

describe("isTerminalState", () => {
  it("detecta estados terminales", () => {
    expect(isTerminalState("done")).toBe(true);
    expect(isTerminalState("failed")).toBe(true);
    expect(isTerminalState("cancelled")).toBe(true);
    expect(isTerminalState("error")).toBe(true);
  });
  it("detecta estados activos", () => {
    expect(isTerminalState("running")).toBe(false);
    expect(isTerminalState("hitl_waiting")).toBe(false);
    expect(isTerminalState(undefined)).toBe(false);
    expect(isTerminalState(null)).toBe(false);
  });
});

describe("useStartRun", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POST /runs y devuelve run_id", async () => {
    vi.mocked(raceApi.startRun).mockResolvedValue({
      run_id: "abc123",
      status: "running",
      started_at: "2026-05-20T10:00:00Z",
      status_url: "/api/race-analysis/runs/abc123/status",
      estimated_seconds: 25,
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useStartRun(), { wrapper });

    let mutateResult: { run_id: string } | undefined;
    await act(async () => {
      mutateResult = await result.current.mutateAsync({
        athlete_id: 1,
        season: 2026,
        valida_nums: [1, 2],
      });
    });

    expect(raceApi.startRun).toHaveBeenCalledWith({
      athlete_id: 1,
      season: 2026,
      valida_nums: [1, 2],
    });
    // mutateAsync resolve devuelve los datos directamente.
    expect(mutateResult?.run_id).toBe("abc123");
    await waitFor(() => expect(result.current.data?.run_id).toBe("abc123"));
  });

  it("propaga errores del backend", async () => {
    vi.mocked(raceApi.startRun).mockRejectedValue(
      new Error("503 AI disabled"),
    );
    const wrapper = createWrapper();
    const { result } = renderHook(() => useStartRun(), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({
          athlete_id: 1,
          season: 2026,
        });
      }),
    ).rejects.toThrow();
    await waitFor(() => expect(result.current.isError).toBe(true));
  });
});

describe("useRunStatus", () => {
  beforeEach(() => vi.clearAllMocks());

  it("hace primer fetch y devuelve evento accumulado", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValueOnce({
      run_id: "r1",
      state: "running",
      progress_pct: 25,
      current_node: "anonymize",
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 20,
      last_seq: 2,
      new_events: [
        {
          seq: 1,
          ts: "2026-05-20T10:00:01Z",
          type: "node_start",
          node: "validate_input",
          payload: {},
        },
        {
          seq: 2,
          ts: "2026-05-20T10:00:02Z",
          type: "node_end",
          node: "validate_input",
          payload: {},
        },
      ],
    });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useRunStatus("r1", { pollIntervalMs: 100000 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.events).toHaveLength(2);
    expect(result.current.data?.latest.state).toBe("running");
  });

  it("se detiene cuando state es terminal", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValueOnce({
      run_id: "r2",
      state: "done",
      progress_pct: 100,
      current_node: null,
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 0,
      last_seq: 5,
      new_events: [],
    });

    const wrapper = createWrapper();
    const { result } = renderHook(
      () => useRunStatus("r2", { pollIntervalMs: 50 }),
      { wrapper },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.latest.state).toBe("done");

    // Espera para asegurar que no hay re-pollings (mock fue llamado 1 vez).
    await new Promise((r) => setTimeout(r, 250));
    expect(raceApi.getRunStatus).toHaveBeenCalledTimes(1);
  });

  it("no se dispara cuando runId es null", () => {
    const wrapper = createWrapper();
    renderHook(() => useRunStatus(null), { wrapper });
    expect(raceApi.getRunStatus).not.toHaveBeenCalled();
  });

  it("respeta enabled=false", () => {
    const wrapper = createWrapper();
    renderHook(() => useRunStatus("r3", { enabled: false }), { wrapper });
    expect(raceApi.getRunStatus).not.toHaveBeenCalled();
  });
});

describe("useApproveStep", () => {
  beforeEach(() => vi.clearAllMocks());

  it("POST decision approve y propaga response", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockResolvedValue({
      accepted: true,
      run_id: "r1",
      step_id: "hitl_review_1",
      next_state: "running",
    });

    const wrapper = createWrapper();
    const { result } = renderHook(() => useApproveStep("r1"), { wrapper });

    let res: { accepted: boolean } | undefined;
    await act(async () => {
      res = await result.current.mutateAsync({
        stepId: "hitl_review_1",
        decision: { decision: "approve" },
      });
    });

    expect(raceApi.submitHITLDecision).toHaveBeenCalledWith(
      "r1",
      "hitl_review_1",
      { decision: "approve" },
    );
    expect(res?.accepted).toBe(true);
    await waitFor(() => expect(result.current.data?.accepted).toBe(true));
  });

  it("propaga errores HTTP", async () => {
    vi.mocked(raceApi.submitHITLDecision).mockRejectedValue(
      new Error("409 Conflict"),
    );

    const wrapper = createWrapper();
    const { result } = renderHook(() => useApproveStep("r1"), { wrapper });

    await expect(
      act(async () => {
        await result.current.mutateAsync({
          stepId: "x",
          decision: { decision: "reject" },
        });
      }),
    ).rejects.toThrow();
  });
});
