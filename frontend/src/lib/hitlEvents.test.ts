import { describe, expect, it } from "vitest";

import { findPendingHitlEvent } from "@/lib/hitlEvents";
import type { RunEvent } from "@/types/raceAnalysis.types";

function evt(seq: number, type: string, node: string | null = null): RunEvent {
  return { seq, ts: "2026-09-16T00:00:00Z", type, node, payload: {} };
}

describe("findPendingHitlEvent", () => {
  it("devuelve el hitl_request vigente", () => {
    const req = evt(3, "hitl_request", "hitl_gate_review");
    expect(findPendingHitlEvent([evt(1, "node_start"), evt(2, "node_end"), req])).toBe(req);
  });

  it("ignora los node_start/node_end del nodo hitl_gate_review (auto-aprobación)", () => {
    expect(
      findPendingHitlEvent([
        evt(1, "node_start", "hitl_gate_review"),
        evt(2, "node_end", "hitl_gate_review"),
        evt(3, "done"),
      ]),
    ).toBeUndefined();
  });

  it("un hitl_response posterior cierra el request", () => {
    expect(
      findPendingHitlEvent([
        evt(1, "hitl_request", "hitl_gate_review"),
        evt(2, "hitl_response", "hitl_gate_review"),
      ]),
    ).toBeUndefined();
  });

  it("sin eventos devuelve undefined", () => {
    expect(findPendingHitlEvent(undefined)).toBeUndefined();
  });
});
