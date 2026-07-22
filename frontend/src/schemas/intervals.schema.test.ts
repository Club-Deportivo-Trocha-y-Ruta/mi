/**
 * Tests para las reglas de `duration_type` del schema de intervalos (feature
 * 034, T012): refinamiento cruzado `refineDurationType` (vía
 * `intervalStructureUpdateInputSchema`, que lo compone junto a
 * `refineRepeatGroups`) y retrocompatibilidad del valor por defecto `fixed`.
 */
import { describe, it, expect } from "vitest";

import { intervalStructureUpdateInputSchema } from "./intervals.schema";

// ---------------------------------------------------------------------------
// Helpers — fixtures mínimos válidos
// ---------------------------------------------------------------------------

function baseFixedBlock(overrides: Record<string, unknown> = {}) {
  return {
    position: 1,
    block_type: "warmup",
    duration_type: "fixed",
    duration_s: 300,
    target_zone: "Z1",
    target_cadence_rpm: 70,
    repeat_group: null,
    repeat_count: null,
    ...overrides,
  };
}

function baseOpenBlock(overrides: Record<string, unknown> = {}) {
  return {
    position: 1,
    block_type: "warmup",
    duration_type: "open_lap",
    duration_s: null,
    target_zone: "Z1",
    target_cadence_rpm: 70,
    repeat_group: null,
    repeat_count: null,
    ...overrides,
  };
}

function baseStructure(blocks: unknown[]) {
  return {
    target_age_band: "13-15",
    age_gate_confirmed: false,
    blocks,
  };
}

// ---------------------------------------------------------------------------
// Suite: bloques fijos (retrocompatibilidad — comportamiento histórico)
// ---------------------------------------------------------------------------

describe("intervalStructureUpdateInputSchema — bloques fijos", () => {
  it("acepta un bloque fijo con duración > 0", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([baseFixedBlock()]),
    );
    expect(result.success).toBe(true);
  });

  it("por defecto (sin duration_type) se trata como fijo — retrocompatibilidad FR-004/FR-011", () => {
    const { duration_type: _omit, ...rest } = baseFixedBlock();
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([rest]),
    );
    expect(result.success).toBe(true);
    if (result.success) {
      expect(result.data.blocks[0].duration_type).toBe("fixed");
    }
  });

  it("rechaza un bloque fijo con duration_s null", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([baseFixedBlock({ duration_s: null })]),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const messages = result.error.issues.map((i) => i.message);
      expect(messages).toContain("La duración debe ser mayor a 0 segundos.");
    }
  });

  it("rechaza un bloque fijo con duration_s <= 0", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([baseFixedBlock({ duration_s: 0 })]),
    );
    expect(result.success).toBe(false);
  });
});

// ---------------------------------------------------------------------------
// Suite: bloques libres (open_lap) — feature 034
// ---------------------------------------------------------------------------

describe("intervalStructureUpdateInputSchema — bloques libres (open_lap)", () => {
  it("acepta un calentamiento libre sin duración", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([
        baseOpenBlock({ block_type: "warmup" }),
        baseFixedBlock({ position: 2 }),
      ]),
    );
    expect(result.success).toBe(true);
  });

  it("acepta un enfriamiento libre sin duración", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([
        baseFixedBlock(),
        baseOpenBlock({ position: 2, block_type: "cooldown" }),
      ]),
    );
    expect(result.success).toBe(true);
  });

  it("rechaza open_lap en un bloque de trabajo", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([baseOpenBlock({ block_type: "work" })]),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const messages = result.error.issues.map((i) => i.message);
      expect(messages).toContain(
        "Solo el calentamiento y el enfriamiento pueden ser libres (hasta botón de vuelta).",
      );
    }
  });

  it("rechaza open_lap en un bloque de recuperación", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([baseOpenBlock({ block_type: "recovery" })]),
    );
    expect(result.success).toBe(false);
  });

  it("rechaza open_lap con repeat_group asignado (orden: libre y luego agrupado)", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([
        baseOpenBlock({ repeat_group: 1, repeat_count: 2 }),
        baseFixedBlock({
          position: 2,
          block_type: "work",
          repeat_group: 1,
          repeat_count: 2,
        }),
      ]),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const messages = result.error.issues.map((i) => i.message);
      expect(messages).toContain(
        "Un bloque libre no puede pertenecer a un grupo repetido.",
      );
    }
  });

  it("rechaza open_lap con duration_s presente", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([baseOpenBlock({ duration_s: 300 })]),
    );
    expect(result.success).toBe(false);
    if (!result.success) {
      const messages = result.error.issues.map((i) => i.message);
      expect(messages).toContain("Un bloque libre no lleva duración.");
    }
  });

  it("una estructura sin ningún bloque fijo (todo libre) es válida si respeta las reglas", () => {
    const result = intervalStructureUpdateInputSchema.safeParse(
      baseStructure([
        baseOpenBlock({ block_type: "warmup" }),
        baseOpenBlock({ position: 2, block_type: "cooldown" }),
      ]),
    );
    expect(result.success).toBe(true);
  });
});
