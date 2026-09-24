import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";

import type { RunEvent, RunState } from "@/types/raceAnalysis.types";

let mockStatus: { latest?: { state: RunState }; events: RunEvent[] } | undefined;
const resetEvents = vi.fn();
const refetch = vi.fn();

vi.mock("@/hooks/ai/useRaceRun", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/hooks/ai/useRaceRun")>();
  return {
    ...actual,
    useRunStatus: () => ({ data: mockStatus, isLoading: false, resetEvents, refetch }),
  };
});

vi.mock("@/components/ai/AnalysisRunTimeline", () => ({
  AnalysisRunTimeline: () => null,
}));

vi.mock("@/components/ai/HITLApprovalCard", () => ({
  HITLApprovalCard: ({
    draftMarkdown,
    familyGapMentions,
  }: {
    draftMarkdown: string;
    familyGapMentions?: string[];
  }) => (
    <div
      data-testid="hitl-card"
      data-gap-mentions={JSON.stringify(familyGapMentions ?? [])}
    >
      {draftMarkdown}
    </div>
  ),
}));

import { GroupRunRow } from "@/components/competitions/insights/GroupRunRow";

const ENTRY = {
  athlete_id: 7,
  name: "Atleta A",
  run_id: "run-1",
  outcome: "started" as const,
  detail: null,
};

function evt(seq: number, type: string, payload: Record<string, unknown> = {}): RunEvent {
  return { seq, ts: "2026-09-16T00:00:00Z", type, node: "hitl_gate_review", payload };
}

describe("GroupRunRow — tarjeta de aprobación", () => {
  beforeEach(() => {
    mockStatus = undefined;
    resetEvents.mockClear();
    refetch.mockClear();
  });

  it("run completado con auto-aprobación: no muestra la tarjeta (antes matcheaba node_start/node_end)", () => {
    mockStatus = {
      latest: { state: "done" },
      events: [evt(1, "node_start"), evt(2, "node_end")],
    };
    render(<GroupRunRow entry={ENTRY} />);
    expect(screen.getByText("Completado")).toBeInTheDocument();
    expect(screen.queryByTestId("hitl-card")).not.toBeInTheDocument();
  });

  it("run terminado con un hitl_request sin respuesta: no muestra la tarjeta (aprobar daría 409)", () => {
    mockStatus = {
      latest: { state: "done" },
      events: [evt(1, "hitl_request", { draft_markdown: "Borrador" })],
    };
    render(<GroupRunRow entry={ENTRY} />);
    expect(screen.queryByTestId("hitl-card")).not.toBeInTheDocument();
  });

  it("run esperando aprobación: muestra el borrador del hitl_request", () => {
    mockStatus = {
      latest: { state: "hitl_waiting" },
      events: [evt(1, "node_start"), evt(2, "hitl_request", { draft_markdown: "Borrador real" })],
    };
    render(<GroupRunRow entry={ENTRY} />);
    expect(screen.getByTestId("hitl-card")).toHaveTextContent("Borrador real");
    expect(resetEvents).not.toHaveBeenCalled();
  });

  // Feature 045 (T062): la fila de análisis grupal reusa la misma tarjeta, así
  // que también le entrega los fragmentos del aviso de brecha con el podio.
  it("le pasa a la tarjeta payload.family_gap_mentions del hitl_request vigente", () => {
    mockStatus = {
      latest: { state: "hitl_waiting" },
      events: [
        evt(1, "hitl_request", {
          draft_markdown: "Borrador",
          family_gap_mentions: ["terminó a 40 s del ganador"],
        }),
      ],
    };
    render(<GroupRunRow entry={ENTRY} />);
    expect(screen.getByTestId("hitl-card")).toHaveAttribute(
      "data-gap-mentions",
      JSON.stringify(["terminó a 40 s del ganador"]),
    );
  });

  it("sin family_gap_mentions en el payload le pasa una lista vacía (sin aviso)", () => {
    mockStatus = {
      latest: { state: "hitl_waiting" },
      events: [evt(1, "hitl_request", { draft_markdown: "Borrador" })],
    };
    render(<GroupRunRow entry={ENTRY} />);
    expect(screen.getByTestId("hitl-card")).toHaveAttribute("data-gap-mentions", "[]");
  });

  it("esperando aprobación sin hitl_request en el buffer: pide un refetch completo una vez", () => {
    mockStatus = { latest: { state: "hitl_waiting" }, events: [evt(1, "node_start")] };
    render(<GroupRunRow entry={ENTRY} />);
    expect(resetEvents).toHaveBeenCalledTimes(1);
    expect(refetch).toHaveBeenCalledTimes(1);
  });
});
