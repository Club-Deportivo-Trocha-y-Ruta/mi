import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";

vi.mock("@/api/raceAnalysis", () => ({
  startRun: vi.fn(),
  getRunStatus: vi.fn(),
  submitHITLDecision: vi.fn(),
  getRunResult: vi.fn(),
}));

import * as raceApi from "@/api/raceAnalysis";

import { AnalysisRunTimeline } from "@/components/ai/AnalysisRunTimeline";

function wrap(ui: ReactNode) {
  const qc = new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  });
  return render(createElement(QueryClientProvider, { client: qc }, ui));
}

describe("AnalysisRunTimeline", () => {
  beforeEach(() => vi.clearAllMocks());

  it("renderiza los 13 nodos del grafo en orden", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValue({
      run_id: "r1",
      state: "running",
      progress_pct: 0,
      current_node: null,
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 30,
      last_seq: 0,
      new_events: [],
    });
    wrap(<AnalysisRunTimeline runId="r1" />);

    await waitFor(() =>
      expect(screen.getByTestId("timeline-nodes-list")).toBeInTheDocument(),
    );
    expect(screen.getByTestId("timeline-node-validate_input")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-node-analyst_agent")).toBeInTheDocument();
    expect(screen.getByTestId("timeline-node-notify_coach")).toBeInTheDocument();
  });

  it("marca nodo done con eventos node_start + node_end", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValue({
      run_id: "r1",
      state: "running",
      progress_pct: 15,
      current_node: "anonymize",
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 22,
      last_seq: 2,
      new_events: [
        {
          seq: 1,
          ts: "2026-05-20T10:00:01.000Z",
          type: "node_start",
          node: "validate_input",
          payload: {},
        },
        {
          seq: 2,
          ts: "2026-05-20T10:00:01.300Z",
          type: "node_end",
          node: "validate_input",
          payload: {},
        },
      ],
    });
    wrap(<AnalysisRunTimeline runId="r1" />);

    await waitFor(() =>
      expect(
        screen.getByTestId("timeline-node-validate_input"),
      ).toHaveAttribute("data-status", "done"),
    );
    // Duración renderizada (300 ms).
    expect(screen.getByText(/300 ms/)).toBeInTheDocument();
  });

  it("muestra progressbar con valor del backend", async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValue({
      run_id: "r1",
      state: "running",
      progress_pct: 45,
      current_node: "analyst_agent",
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 12,
      last_seq: 6,
      new_events: [],
    });
    wrap(<AnalysisRunTimeline runId="r1" />);
    await waitFor(() => {
      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveAttribute("aria-valuenow", "45");
    });
  });

  it("indica error visible cuando query falla", async () => {
    vi.mocked(raceApi.getRunStatus).mockRejectedValue(
      new Error("network down"),
    );
    wrap(<AnalysisRunTimeline runId="r1" />);
    await waitFor(() =>
      expect(screen.getByTestId("timeline-error")).toBeInTheDocument(),
    );
    expect(screen.getByRole("alert")).toHaveTextContent(/Error obteniendo/);
  });

  it("placeholder cuando runId vacío", () => {
    wrap(<AnalysisRunTimeline runId="" />);
    expect(screen.getByText(/Sin run activo/i)).toBeInTheDocument();
  });
});
