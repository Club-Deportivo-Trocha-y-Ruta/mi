/**
 * Schema Zod del registro antropométrico (`AnthropometricRecord`).
 *
 * Mirror 1:1 de `frontend/src/types/anthropometry.types.ts` /
 * `backend/app/schemas/anthropometry.py::AnthropometryOut`. Sigue el mismo
 * patrón de `schemas/stageLog.ts`: se usa para `.parse()` las respuestas de
 * la API en tests/MSW y como allowlist de defensa en profundidad (si el
 * backend filtrara accidentalmente un campo no declarado, Zod lo descarta).
 *
 * No existía un schema de anthropometry en este directorio antes de la
 * feature 040 — se crea aquí porque `growth_source` (columna nueva,
 * `contracts/anthropometry-source.md`) necesita quedar validado en el mismo
 * lugar que el resto del registro.
 */

import { z } from "zod";

import { MaturationStatus } from "@/types/enums";

// ---------------------------------------------------------------------------
// Sub-schemas
// ---------------------------------------------------------------------------

/** Referencia poblacional del cálculo almacenado. `null` = registro legado (feature 040). */
export const growthSourceSchema = z.union([z.literal("WHO"), z.literal("CDC"), z.null()]);

export const bikeFitCategorySchema = z.enum(["short_reach", "standard", "long_reach"]);

export const morphologyMetricsSchema = z.object({
  ape_index: z.number(),
  arm_span_height_delta_cm: z.number(),
  posture_screening_flag: z.boolean(),
  posture_screening_message: z.string().nullable(),
  bike_fit_category: bikeFitCategorySchema,
  bike_fit_guidance: z.string(),
  ape_index_advisory: z.string().nullable(),
});

// ---------------------------------------------------------------------------
// Registro antropométrico
// ---------------------------------------------------------------------------

export const anthropometricRecordSchema = z.object({
  id: z.number(),
  athlete_id: z.number(),
  evaluation_date: z.string(),
  weight_kg: z.number(),
  standing_height_cm: z.number(),
  arm_span_cm: z.number().nullable(),
  sitting_height_cm: z.number(),
  leg_length_cm: z.number(),
  leg_sitting_ratio: z.number(),
  maturity_offset: z.number(),
  age_at_phv: z.number(),
  maturation_status: z.nativeEnum(MaturationStatus),
  training_implications: z.string().nullable(),
  evaluated_by: z.number(),
  created_at: z.string(),
  notes: z.string().nullable(),
  // Percentiles de crecimiento (calculados por el backend; opcionales en
  // registros históricos que aún no tienen estos campos poblados).
  height_z_score: z.number().nullable().optional(),
  height_percentile: z.number().nullable().optional(),
  bmi: z.number().nullable().optional(),
  bmi_z_score: z.number().nullable().optional(),
  bmi_percentile: z.number().nullable().optional(),
  weight_z_score: z.number().nullable().optional(),
  weight_percentile: z.number().nullable().optional(),
  nutritional_status: z.string().nullable().optional(),
  morphology: morphologyMetricsSchema.nullable().optional(),
  /** Referencia usada para los campos anteriores (feature 040). */
  growth_source: growthSourceSchema.optional(),
});

export type AnthropometricRecordParsed = z.infer<typeof anthropometricRecordSchema>;
