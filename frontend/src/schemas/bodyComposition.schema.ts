/**
 * Schemas Zod de composición corporal por pliegues (feature 046).
 *
 * Dos usos distintos, deliberadamente separados:
 * 1. `skinfoldSetOutSchema` / `bodyCompositionOutSchema` / ... — mirror 1:1
 *    de las respuestas del backend (`contracts/skinfolds-api.md`), usados
 *    con `.parse()` en `api/bodyComposition.ts` como allowlist de defensa en
 *    profundidad (mismo patrón que `schemas/anthropometry.schema.ts`).
 * 2. `skinfoldWizardFormSchema` — schema de **formulario** (RHF) para el
 *    wizard de captura; valida lo que el coach escribe antes de armar el
 *    `SkinfoldSetIn` que viaja al backend. No es un mirror del contrato de
 *    salida: acepta valores intermedios de UI (p. ej. un input vacío).
 *
 * Validación de lecturas: 2.0–60.0 mm, un solo decimal, múltiplos de 0.5
 * (medio milímetro) — igual que `SkinfoldSiteIn` en
 * `backend/app/schemas/body_composition.py`.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Sitios
// ---------------------------------------------------------------------------

export const skinfoldSiteSchema = z.enum([
  "triceps",
  "biceps",
  "subscapular",
  "medial_calf",
  "iliac_crest",
  "supraspinale",
]);

/** Medio milímetro: valor con a lo sumo un decimal, múltiplo de 0.5. */
const halfMillimetreReading = z
  .number()
  .min(2.0)
  .max(60.0)
  .refine((v) => Math.abs(v * 2 - Math.round(v * 2)) < 1e-9, {
    message: "Debe ser un múltiplo de 0.5 mm",
  });

// ---------------------------------------------------------------------------
// Mirror de la API (entrada/salida)
// ---------------------------------------------------------------------------

export const skinfoldSiteInSchema = z.discriminatedUnion("declined", [
  z.object({ declined: z.literal(true) }),
  z.object({
    declined: z.literal(false).optional(),
    readings: z.array(halfMillimetreReading).min(2).max(3),
  }),
]);

export const skinfoldSetInSchema = z.object({
  caliper_model: z.string(),
  sites: z.record(skinfoldSiteSchema, skinfoldSiteInSchema),
});

export const skinfoldSiteOutSchema = z.object({
  value_mm: z.number().nullable(),
  readings: z.array(z.number()).nullable(),
  declined: z.boolean(),
  unconfirmed: z.boolean(),
});

export const skinfoldSetOutSchema = z.object({
  record_id: z.number(),
  athlete_id: z.number(),
  evaluation_date: z.string(),
  caliper_model: z.string(),
  protocol_version: z.string(),
  sites: z.record(skinfoldSiteSchema, skinfoldSiteOutSchema),
  sum4_mm: z.number().nullable(),
  sum6_mm: z.number().nullable(),
  body_fat_pct: z.number().nullable(),
  fat_mass_kg: z.number().nullable(),
  fat_free_mass_kg: z.number().nullable(),
  equation_version: z.string().nullable(),
  margin_pct: z.number(),
  measured_by: z.number(),
  updated_at: z.string(),
  needs_third_reading_unconfirmed: z.array(skinfoldSiteSchema).default([]),
});

export const sumChangeCodeSchema = z.enum([
  "none",
  "within_noise",
  "up_real",
  "down_real",
]);

export const coachBandSchema = z.enum(["verde", "ambar", "rojo"]);
/** Nunca `rojo` — proyección familiar (contract §3c). */
export const familyBandSchema = z.enum(["verde", "ambar"]);

export const bandReasonCodeSchema = z.enum([
  "no_real_change",
  "expected_pubertal_gain",
  "pre_spurt_accumulation",
  "post_phv_lean_gain",
  "first_set",
  "stable",
  "sum_up_unexplained",
  "sum_up_velocity_low",
  "sum_down_unexplained",
  "reference_extreme",
  "bmi_z_drop",
  "velocity_low_persistent",
  "energy_availability_pattern",
]);

export const legMissingSchema = z.enum([
  "weight",
  "height",
  "velocity",
  "bmi_z",
  "reference",
  "previous_set",
]);

export const referencePointSchema = z.object({
  percentile: z.number().nullable(),
  code: z.enum(["low_extreme", "low", "normal", "high", "high_extreme", "unavailable"]),
});

export const bodyCompositionReadingSchema = z.object({
  sets_count: z.number(),
  sum4_change_mm: z.number().nullable(),
  sum6_change_mm: z.number().nullable(),
  sum_change_code: sumChangeCodeSchema,
  weight_change_code: z.enum(["up", "flat_or_down", "unavailable"]),
  height_growth_code: z.enum(["growing", "stalled", "unavailable"]),
  velocity_code: z.enum(["within_or_above", "below", "unavailable"]),
  bmi_z_change_code: z.enum(["ok", "drop_moderate", "drop_large", "unavailable"]),
  reference_triceps: referencePointSchema,
  reference_subscapular: referencePointSchema,
  ffm_trend_code: z.enum(["up", "flat", "down", "unavailable"]),
  sites_declined_count: z.number(),
  band: coachBandSchema,
  family_band: familyBandSchema,
  latest_attempt_declined: z.string().nullable(),
  band_reason_code: bandReasonCodeSchema,
  legs_missing: z.array(legMissingSchema),
  next_due_date: z.string().nullable(),
  days_until_due: z.number().nullable(),
});

const seriesPointSchema = z.object({ date: z.string(), value: z.number() });

export const bodyCompositionSeriesSchema = z.object({
  sum4: z.array(seriesPointSchema),
  sum6: z.array(seriesPointSchema),
  per_site: z.record(skinfoldSiteSchema, z.array(seriesPointSchema)),
});

export const bodyCompositionEstimatesLatestSchema = z.object({
  body_fat_pct: z.number().nullable(),
  fat_mass_kg: z.number().nullable(),
  fat_free_mass_kg: z.number().nullable(),
  equation_version: z.string().nullable(),
  margin_pct: z.number(),
});

export const bodyCompositionReferenceInfoSchema = z.object({
  source: z.string(),
  population: z.string(),
  side: z.string(),
  age_range: z.string(),
});

export const bodyCompositionOutSchema = z.object({
  athlete_id: z.number(),
  sets: z.array(skinfoldSetOutSchema),
  series: bodyCompositionSeriesSchema.nullable(),
  reading: bodyCompositionReadingSchema.nullable(),
  estimates_latest: bodyCompositionEstimatesLatestSchema.nullable(),
  reference: bodyCompositionReferenceInfoSchema.nullable(),
  next_due_date: z.string().nullable(),
});

export const bodyCompositionSummarySchema = z.object({
  has_data: z.boolean(),
  latest_set_date: z.string().nullable(),
  // Sin pliegues (`has_data=false`) el backend envía estas claves en `null`.
  band: coachBandSchema.nullable(),
  family_band: familyBandSchema.nullable(),
  family_label: z.string().nullable(),
  family_sentence: z.string().nullable(),
  next_due_date: z.string().nullable(),
  days_until_due: z.number().nullable(),
  latest_attempt_declined: z.string().nullable(),
  coach_reason: z.string().nullable(),
  sum4_mm: z.number().nullable(),
  sum4_change_mm: z.number().nullable(),
  sum_change_code: sumChangeCodeSchema.nullable(),
  sum6_mm: z.number().nullable(),
  body_fat_pct: z.number().nullable(),
  fat_free_mass_kg: z.number().nullable(),
  legs_missing: z.array(legMissingSchema),
});

/**
 * Vista de familia — exactamente estas cinco claves
 * (`contracts/skinfolds-api.md` §5). `.strict()` para que un campo extra
 * filtrado por error del backend (p. ej. `band`) haga fallar el parse en
 * vez de propagarse a la UI.
 */
export const bodyCompositionFamilySummarySchema = z
  .object({
    has_data: z.boolean(),
    latest_set_date: z.string().nullable(),
    family_band: familyBandSchema.nullable(),
    family_label: z.string().nullable(),
    family_sentence: z.string().nullable(),
  })
  .strict();

export const bodyCompositionSummaryOutSchema = z.union([
  bodyCompositionSummarySchema,
  bodyCompositionFamilySummarySchema,
]);

export const bodyCompositionNewsletterBlockSchema = z.object({
  family_label: z.string(),
  family_sentence: z.string(),
  notice_text: z.string(),
});

// ---------------------------------------------------------------------------
// Formulario del wizard (RHF)
// ---------------------------------------------------------------------------

/** Un sitio del wizard: se omitió o trae 2–3 lecturas numéricas válidas. */
export const skinfoldWizardSiteSchema = z.discriminatedUnion("declined", [
  z.object({ declined: z.literal(true) }),
  z.object({
    declined: z.literal(false),
    readings: z
      .array(halfMillimetreReading)
      .min(2, "Se necesitan al menos dos lecturas")
      .max(3, "Máximo tres lecturas"),
  }),
]);

export const skinfoldWizardFormSchema = z.object({
  caliper_model: z.string().min(1).default("slim_guide"),
  sites: z.object({
    triceps: skinfoldWizardSiteSchema,
    biceps: skinfoldWizardSiteSchema,
    subscapular: skinfoldWizardSiteSchema,
    medial_calf: skinfoldWizardSiteSchema,
    iliac_crest: skinfoldWizardSiteSchema,
    supraspinale: skinfoldWizardSiteSchema,
  }),
});

export type SkinfoldWizardFormValues = z.infer<typeof skinfoldWizardFormSchema>;
