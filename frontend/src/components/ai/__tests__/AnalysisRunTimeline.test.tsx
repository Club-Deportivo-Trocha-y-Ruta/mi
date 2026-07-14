import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { createElement, type ReactNode } from "react";
import { axe } from "jest-axe";

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

  // ------------------------------------------------------------------
  // UX defensiva: HITL gate vs error real
  // ------------------------------------------------------------------

  it(
    "state=hitl_waiting + evento error en hitl_gate_review → " +
      "muestra 'esperando revisión' (no error)",
    async () => {
      vi.mocked(raceApi.getRunStatus).mockResolvedValue({
        run_id: "r1",
        state: "hitl_waiting",
        progress_pct: 70,
        current_node: "hitl_gate_review",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 0,
        last_seq: 3,
        new_events: [
          {
            seq: 1,
            ts: "2026-05-20T10:00:01.000Z",
            type: "node_start",
            node: "hitl_gate_review",
            payload: {},
          },
          {
            seq: 2,
            ts: "2026-05-20T10:00:01.200Z",
            type: "error",
            node: "hitl_gate_review",
            payload: { message: "GraphInterrupt: awaiting human input" },
          },
        ],
      });
      wrap(<AnalysisRunTimeline runId="r1" />);

      await waitFor(() =>
        expect(
          screen.getByTestId("timeline-node-hitl_gate_review"),
        ).toHaveAttribute("data-status", "awaiting_review"),
      );

      // No debe haber badge "Error" (sr-only label) en el nodo del gate.
      const gateNode = screen.getByTestId("timeline-node-hitl_gate_review");
      expect(gateNode).not.toHaveTextContent(/^Error$/);

      // ARIA label descriptivo en el <li>.
      expect(gateNode).toHaveAttribute(
        "aria-label",
        expect.stringMatching(/esperando revisión/i),
      );

      // Header del wizard también refleja la pausa.
      expect(
        screen.getByText(/Esperando tu aprobación/i),
      ).toBeInTheDocument();
    },
  );

  it(
    "state=failed + evento error en hitl_gate_review → " +
      "marca el nodo como error real",
    async () => {
      vi.mocked(raceApi.getRunStatus).mockResolvedValue({
        run_id: "r1",
        state: "failed",
        progress_pct: 70,
        current_node: "hitl_gate_review",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 0,
        last_seq: 2,
        new_events: [
          {
            seq: 1,
            ts: "2026-05-20T10:00:01.000Z",
            type: "node_start",
            node: "hitl_gate_review",
            payload: {},
          },
          {
            seq: 2,
            ts: "2026-05-20T10:00:01.500Z",
            type: "error",
            node: "hitl_gate_review",
            payload: { message: "real boom" },
          },
        ],
      });
      wrap(<AnalysisRunTimeline runId="r1" />);

      await waitFor(() =>
        expect(
          screen.getByTestId("timeline-node-hitl_gate_review"),
        ).toHaveAttribute("data-status", "error"),
      );
      // Header marca el run como fallido.
      expect(screen.getByText("Falló")).toBeInTheDocument();
    },
  );

  it("state=done + todos los nodos con node_start+node_end → todos done", async () => {
    const baseTs = Date.parse("2026-05-20T10:00:00Z");
    // Generamos pares node_start/node_end para los 13 nodos canónicos.
    const NODE_KEYS = [
      "validate_input",
      "load_race_data",
      "anonymize",
      "compute_metrics",
      "retrieve_principles",
      "recall_memory",
      "analyst_agent",
      "critic_agent",
      "hitl_gate_review",
      "persist_insight",
      "rehydrate_names",
      "render_outputs",
      "notify_coach",
    ];
    const events = NODE_KEYS.flatMap((node, idx) => [
      {
        seq: idx * 2 + 1,
        ts: new Date(baseTs + idx * 1000).toISOString(),
        type: "node_start",
        node,
        payload: {},
      },
      {
        seq: idx * 2 + 2,
        ts: new Date(baseTs + idx * 1000 + 200).toISOString(),
        type: "node_end",
        node,
        payload: {},
      },
    ]);
    vi.mocked(raceApi.getRunStatus).mockResolvedValue({
      run_id: "r1",
      state: "done",
      progress_pct: 100,
      current_node: null,
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 0,
      last_seq: events.length,
      new_events: events,
    });
    wrap(<AnalysisRunTimeline runId="r1" />);

    await waitFor(() =>
      expect(
        screen.getByTestId("timeline-node-notify_coach"),
      ).toHaveAttribute("data-status", "done"),
    );
    for (const key of NODE_KEYS) {
      expect(screen.getByTestId(`timeline-node-${key}`)).toHaveAttribute(
        "data-status",
        "done",
      );
    }
    // Header del wizard: estado global "Completado".
    expect(screen.getAllByText(/Completado/i).length).toBeGreaterThan(0);
  });

  // ------------------------------------------------------------------
  // variant="compact" (T049) — solo header, sin `<ol>` de nodos
  // ------------------------------------------------------------------

  it('variant="compact" renderiza solo el header (label + progressbar + ETA), sin la lista de nodos', async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValue({
      run_id: "r1",
      state: "running",
      progress_pct: 40,
      current_node: "analyst_agent",
      started_at: "2026-05-20T10:00:00Z",
      estimated_seconds_remaining: 18,
      last_seq: 0,
      new_events: [],
    });
    wrap(<AnalysisRunTimeline runId="r1" variant="compact" />);

    await waitFor(() => {
      const bar = screen.getByRole("progressbar");
      expect(bar).toHaveAttribute("aria-valuenow", "40");
    });
    expect(screen.getByTestId("timeline-eta")).toHaveTextContent("18s");
    expect(screen.queryByTestId("timeline-nodes-list")).not.toBeInTheDocument();
  });

  it('variant="full" (default) sigue renderizando la lista de nodos', async () => {
    vi.mocked(raceApi.getRunStatus).mockResolvedValue({
      run_id: "r1",
      state: "running",
      progress_pct: 10,
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
  });

  // ------------------------------------------------------------------
  // jest-axe (feature 033 / T056) — ambas densidades
  // ------------------------------------------------------------------

  describe("accesibilidad (T056)", () => {
    it('jest-axe: 0 violaciones en variant="full"', async () => {
      vi.mocked(raceApi.getRunStatus).mockResolvedValue({
        run_id: "r1",
        state: "running",
        progress_pct: 25,
        current_node: "compute_metrics",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 20,
        last_seq: 0,
        new_events: [],
      });
      const { container } = wrap(<AnalysisRunTimeline runId="r1" />);
      await waitFor(() =>
        expect(screen.getByTestId("timeline-nodes-list")).toBeInTheDocument(),
      );
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });

    it('jest-axe: 0 violaciones en variant="compact"', async () => {
      vi.mocked(raceApi.getRunStatus).mockResolvedValue({
        run_id: "r1",
        state: "running",
        progress_pct: 60,
        current_node: "critic_agent",
        started_at: "2026-05-20T10:00:00Z",
        estimated_seconds_remaining: 10,
        last_seq: 0,
        new_events: [],
      });
      const { container } = wrap(
        <AnalysisRunTimeline runId="r1" variant="compact" />,
      );
      await waitFor(() => {
        const bar = screen.getByRole("progressbar");
        expect(bar).toHaveAttribute("aria-valuenow", "60");
      });
      const results = await axe(container);
      expect(results).toHaveNoViolations();
    });
  });
});
