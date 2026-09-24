import { describe, expect, it } from "vitest";

import {
  familyGapMentionsFromEvent,
  findPendingHitlEvent,
} from "@/lib/hitlEvents";
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

describe("familyGapMentionsFromEvent (feature 045, T062)", () => {
  function withPayload(payload: Record<string, unknown>): RunEvent {
    return {
      seq: 1,
      ts: "2026-09-23T00:00:00Z",
      type: "hitl_request",
      node: "hitl_gate_review",
      payload,
    };
  }

  it("devuelve los fragmentos de payload.family_gap_mentions", () => {
    expect(
      familyGapMentionsFromEvent(
        withPayload({
          family_gap_mentions: ["terminó a 40 s del ganador", "lejos del podio"],
        }),
      ),
    ).toEqual(["terminó a 40 s del ganador", "lejos del podio"]);
  });

  it("[] cuando la clave es [] (borrador sin menciones)", () => {
    expect(
      familyGapMentionsFromEvent(withPayload({ family_gap_mentions: [] })),
    ).toEqual([]);
  });

  it("[] cuando la clave falta (backend previo a la 045 o hitl_required legado)", () => {
    expect(familyGapMentionsFromEvent(withPayload({ step_id: "s1" }))).toEqual([]);
  });

  it("[] sin evento", () => {
    expect(familyGapMentionsFromEvent(undefined)).toEqual([]);
  });

  it("descarta entradas no textuales o vacías y un valor que no es lista", () => {
    expect(
      familyGapMentionsFromEvent(
        withPayload({ family_gap_mentions: ["ok", 3, null, "  ", ""] }),
      ),
    ).toEqual(["ok"]);
    expect(
      familyGapMentionsFromEvent(withPayload({ family_gap_mentions: "podio" })),
    ).toEqual([]);
  });
});
