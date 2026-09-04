/**
 * Schema Zod de `GrowthSummary` (feature 040, US2).
 *
 * Mirror 1:1 de `contracts/growth-summary-api.md` /
 * `backend/app/schemas/growth.py::GrowthSummaryOut` (T033, en construcción en
 * paralelo — el contrato es la fuente de verdad hasta que ese archivo
 * exista). Sigue el mismo patrón de `schemas/intervals.schema.ts`: cada
 * respuesta del servidor se valida con `.parse()` en `api/growth.ts`, y
 * `.strip()` descarta cualquier clave no declarada (defensa en profundidad —
 * Ley 1581: el endpoint nunca debería devolver nombre/fecha de
 * nacimiento/notas, pero si lo hiciera por error, el cliente no los retiene).
 *
 * `nutritionalStatusSchema` reutiliza exactamente el vocabulario de 9 valores
 * de `lib/growth/bands.ts::NutritionalStatus` (enum `NutritionalStatus` del
 * backend) — anclado vía `z.ZodType<NutritionalStatus>` para que ambos no
 * puedan divergir sin un error de compilación.
 */

import { z } from "zod";

import { MaturationStatus } from "@/types/enums";
import { growthSourceSchema } from "@/schemas/anthropometry.schema";
import type { NutritionalStatus } from "@/lib/growth/bands";

// ---------------------------------------------------------------------------
// Vocabularios compartidos
// ---------------------------------------------------------------------------

/** Banda nutricional (talla/IMC/peso) — igual a `lib/growth/bands.ts::NutritionalStatus`. */
export const nutritionalStatusSchema: z.ZodType<NutritionalStatus> = z.enum([
  "retraso_talla",
  "riesgo_retraso_talla",
  "talla_adecuada",
  "talla_alta",
  "delgadez_severa",
  "delgadez",
  "adecuado",
  "sobrepeso",
  "obesidad",
]);

/** Igual a `types/alerts.types.ts::MeasurementStatus`. */
export const measurementStatusSchema = z.enum([
  "ok",
  "due_soon",
  "overdue",
  "never",
]);

/**
 * Alertas de `GrowthSummary` (data-model.md §3). Superconjunto del
 * `GrowthAlert` de `types/alerts.types.ts` (ese tipo solo cubre 3 de las 6 —
 * es del endpoint de alertas del dashboard, no de este resumen).
 */
export const growthSummaryAlertSchema = z.enum([
  "circa_phv",
  "height_p3",
  "bmi_p3",
  "rapid_growth",
  "approaching_circa",
  "phase_changed",
]);

// ---------------------------------------------------------------------------
// Sub-schemas de GrowthSummary
// ---------------------------------------------------------------------------

/** Lectura de banda para un indicador (talla/IMC/peso). `null` cuando no hay referencia para la edad. */
export const bandReadingSchema = z
  .object({
    value: z.number(),
    z_score: z.number(),
    percentile: z.number(),
    band: nutritionalStatusSchema,
  })
  .strip();

export const latestBandsSchema = z
  .object({
    record_id: z.number(),
    growth_source: growthSourceSchema,
    height: bandReadingSchema.nullable(),
    bmi: bandReadingSchema.nullable(),
    /** Solo presente cuando la edad en la evaluación es <= 120.5 meses. */
    weight: bandReadingSchema.nullable(),
  })
  .strip();

/** `null` cuando hay menos de 2 registros. */
export const growthVelocitySchema = z
  .object({
    cm_per_month: z.number(),
    cm_per_year: z.number(),
    window_days: z.number().int(),
    /** `window_days < 30` — suprime la alerta `rapid_growth`. */
    interval_short: z.boolean(),
    /** `[min, max]` orientativo por etapa/sexo (research.md R-05). */
    expected_cm_per_year: z.tuple([z.number(), z.number()]),
  })
  .strip();

export const measurementDueSchema = z
  .object({
    status: measurementStatusSchema,
    interval_days: z.number().int(),
    next_due_date: z.string().nullable(),
    days_overdue: z.number().int().nullable(),
  })
  .strip();

// ---------------------------------------------------------------------------
// GrowthSummary — respuesta completa
// ---------------------------------------------------------------------------

export const growthSummarySchema = z
  .object({
    athlete_id: z.number(),
    /** Fecha del servidor (hoy), para el cómputo de "hace N meses" en el cliente. */
    computed_at: z.string(),
    records_count: z.number().int(),
    latest_evaluation_date: z.string().nullable(),
    stage: z.nativeEnum(MaturationStatus).nullable(),
    maturity_offset: z.number().nullable(),
    age_at_phv: z.number().nullable(),
    /** (edad hoy − edad en PHV) × 12, 1 decimal; negativo = antes del PHV. */
    months_from_phv: z.number().nullable(),
    velocity: growthVelocitySchema.nullable(),
    measurement: measurementDueSchema,
    alerts: z.array(growthSummaryAlertSchema),
    latest: latestBandsSchema.nullable(),
  })
  .strip();

export type GrowthSummaryParsed = z.infer<typeof growthSummarySchema>;
