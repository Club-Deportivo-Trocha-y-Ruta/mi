import { describe, expect, it } from "vitest";

import { applyOverrides, clearOverrideBlock } from "@/lib/applyOverrides";
import { buildStageLogFullMonth } from "@/test/fixtures/stageLog";

describe("applyOverrides", () => {
  it("devuelve el stageLog original cuando no hay overrides", () => {
    const stageLog = buildStageLogFullMonth();
    expect(applyOverrides(stageLog, null)).toBe(stageLog);
    expect(applyOverrides(stageLog, undefined)).toBe(stageLog);
  });

  it("no muta el stageLog original", () => {
    const stageLog = buildStageLogFullMonth();
    const snapshot = JSON.parse(JSON.stringify(stageLog));
    applyOverrides(stageLog, { stage_title: "Otro título" });
    expect(stageLog).toEqual(snapshot);
  });

  it("reemplaza stage_title cuando hay override", () => {
    const stageLog = buildStageLogFullMonth();
    const merged = applyOverrides(stageLog, { stage_title: "Título editado por el coach" });
    expect(merged.stage_title).toBe("Título editado por el coach");
    // el resto de los campos permanece igual
    expect(merged.observations).toBe(stageLog.observations);
  });

  it("fusiona summit_caption dentro de summit sin tocar el resto de summit", () => {
    const stageLog = buildStageLogFullMonth();
    const merged = applyOverrides(stageLog, { summit_caption: "Caption editado" });
    expect(merged.summit?.caption).toBe("Caption editado");
    expect(merged.summit?.title).toBe(stageLog.summit?.title);
  });

  it("ignora summit_caption cuando el stageLog no tiene summit", () => {
    const stageLog = buildStageLogFullMonth({ summit: null });
    const merged = applyOverrides(stageLog, { summit_caption: "Caption editado" });
    expect(merged.summit).toBeNull();
  });

  it("reemplaza observations completas", () => {
    const stageLog = buildStageLogFullMonth();
    const newObservations = [
      { claim: "Nueva observación", evidence: "1 dato", block_ref: "attendance" as const },
    ];
    const merged = applyOverrides(stageLog, { observations: newObservations });
    expect(merged.observations).toEqual(newObservations);
  });

  it("fusiona analyst_reading preservando source_insight_id", () => {
    const stageLog = buildStageLogFullMonth();
    const merged = applyOverrides(stageLog, {
      analyst_reading: { headline_family: "Nuevo headline", action_family: "Nueva acción" },
    });
    expect(merged.analyst_reading?.headline_family).toBe("Nuevo headline");
    expect(merged.analyst_reading?.action_family).toBe("Nueva acción");
    expect(merged.analyst_reading?.source_insight_id).toBe(
      stageLog.analyst_reading?.source_insight_id,
    );
  });

  it("ignora analyst_reading override cuando el stageLog no tiene analyst_reading", () => {
    const stageLog = buildStageLogFullMonth({ analyst_reading: null });
    const merged = applyOverrides(stageLog, {
      analyst_reading: { headline_family: "x", action_family: "y" },
    });
    expect(merged.analyst_reading).toBeNull();
  });

  it("fusiona next_segment_text dentro de next_segment", () => {
    const stageLog = buildStageLogFullMonth();
    const merged = applyOverrides(stageLog, { next_segment_text: "Texto editado" });
    expect(merged.next_segment?.text).toBe("Texto editado");
    expect(merged.next_segment?.focus_groups).toEqual(stageLog.next_segment?.focus_groups);
  });

  it("reemplaza family_compass completo", () => {
    const stageLog = buildStageLogFullMonth();
    const newCompass = {
      conversation_question: "¿Nueva pregunta?",
      monthly_challenge: "Nuevo reto",
      what_to_watch: "Nuevo foco",
    };
    const merged = applyOverrides(stageLog, { family_compass: newCompass });
    expect(merged.family_compass).toEqual(newCompass);
  });

  it("aplica varios overrides simultáneamente", () => {
    const stageLog = buildStageLogFullMonth();
    const merged = applyOverrides(stageLog, {
      stage_title: "Título editado",
      summit_caption: "Caption editado",
    });
    expect(merged.stage_title).toBe("Título editado");
    expect(merged.summit?.caption).toBe("Caption editado");
  });
});

describe("clearOverrideBlock", () => {
  it("devuelve un objeto vacío cuando no hay overrides previos", () => {
    expect(clearOverrideBlock(null, "stage_title")).toEqual({});
    expect(clearOverrideBlock(undefined, "stage_title")).toEqual({});
  });

  it("elimina solo la clave del bloque indicado", () => {
    const overrides = {
      stage_title: "Título editado",
      summit_caption: "Caption editado",
    };
    const cleared = clearOverrideBlock(overrides, "stage_title");
    expect(cleared).toEqual({ summit_caption: "Caption editado" });
  });

  it("no muta el objeto de overrides original", () => {
    const overrides = { stage_title: "Título editado" };
    const snapshot = { ...overrides };
    clearOverrideBlock(overrides, "stage_title");
    expect(overrides).toEqual(snapshot);
  });

  it("es un no-op si el bloque no estaba en overrides", () => {
    const overrides = { summit_caption: "Caption editado" };
    const cleared = clearOverrideBlock(overrides, "stage_title");
    expect(cleared).toEqual(overrides);
  });
});
