import { describe, expect, it } from "vitest";

import { bodyCompositionSummaryOutSchema } from "@/schemas/bodyComposition.schema";

/**
 * Regresión: con un deportista sin pliegues el backend responde el bloque
 * `body_composition` de growth-summary con `has_data=false` y el resto de
 * claves en `null`. Antes el parse fallaba y toda la pestaña Crecimiento
 * mostraba "No se pudo cargar el resumen de crecimiento".
 */
describe("bodyCompositionSummaryOutSchema — sin datos", () => {
  it("acepta el bloque del coach con has_data=false y claves en null", () => {
    const coachNoData = {
      has_data: false,
      latest_set_date: null,
      band: null,
      family_band: null,
      family_label: null,
      family_sentence: null,
      next_due_date: null,
      days_until_due: null,
      latest_attempt_declined: null,
      coach_reason: null,
      sum4_mm: null,
      sum4_change_mm: null,
      sum_change_code: null,
      sum6_mm: null,
      body_fat_pct: null,
      fat_free_mass_kg: null,
      legs_missing: [],
    };
    expect(bodyCompositionSummaryOutSchema.safeParse(coachNoData).success).toBe(true);
  });

  it("acepta el bloque de familia (cinco claves) con has_data=false", () => {
    const familyNoData = {
      has_data: false,
      latest_set_date: null,
      family_band: null,
      family_label: null,
      family_sentence: null,
    };
    expect(bodyCompositionSummaryOutSchema.safeParse(familyNoData).success).toBe(true);
  });

  it("sigue rechazando rojo como banda de familia", () => {
    const familyRojo = {
      has_data: true,
      latest_set_date: "2026-09-01",
      family_band: "rojo",
      family_label: "Requiere acompañamiento profesional",
      family_sentence: "x",
    };
    expect(bodyCompositionSummaryOutSchema.safeParse(familyRojo).success).toBe(false);
  });
});
