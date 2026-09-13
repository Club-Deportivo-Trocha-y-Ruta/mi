/**
 * Tipos de `GrowthSummary` (feature 040, US2).
 *
 * Se infieren de los schemas Zod (`schemas/growth.schemas.ts`), que son la
 * fuente única de verdad de las formas de datos (`contracts/growth-summary-api.md`).
 * Mismo patrón que `types/intervals.types.ts`.
 */

import type { z } from "zod";

import type {
  bandReadingSchema,
  growthSummaryAlertSchema,
  growthSummarySchema,
  growthVelocitySchema,
  latestAiAnalysisSchema,
  latestBandsSchema,
  measurementDueSchema,
  measurementStatusSchema,
  nutritionalStatusSchema,
} from "@/schemas/growth.schemas";

export type NutritionalStatusBand = z.infer<typeof nutritionalStatusSchema>;
export type GrowthMeasurementStatus = z.infer<typeof measurementStatusSchema>;

/**
 * Alertas del resumen de crecimiento (data-model.md §3). Superconjunto del
 * `GrowthAlert` de `types/alerts.types.ts` (endpoint de alertas del
 * dashboard, distinto de este resumen por-atleta).
 */
export type GrowthSummaryAlert = z.infer<typeof growthSummaryAlertSchema>;

export type BandReading = z.infer<typeof bandReadingSchema>;
export type LatestBands = z.infer<typeof latestBandsSchema>;
export type GrowthVelocity = z.infer<typeof growthVelocitySchema>;
export type MeasurementDue = z.infer<typeof measurementDueSchema>;

/**
 * Resumen del último análisis de IA por medición, embebido en
 * `GrowthSummary` (feature 042, `contracts/growth-summary-latest-analysis.md`).
 *
 * SIEMPRE tratar `GrowthSummary["latest_ai_analysis"]` como
 * `LatestAiAnalysis | null | undefined` — nunca asumir que existe. Es
 * `null`/`undefined` cuando no hay análisis generado aún, falta
 * consentimiento, la IA está deshabilitada, o quien mira es un padre y la
 * fila no quedó `approved`/`revised` (compuerta familiar, FR-016). Un
 * `critic_verdict` ausente o `null` significa "no visible para este rol",
 * no "sin veredicto" — el backend siempre corrió el pipeline si el objeto
 * existe.
 */
export type LatestAiAnalysis = z.infer<typeof latestAiAnalysisSchema>;

/** `GET /api/athletes/{id}/growth-summary` — resumen derivado, nunca persistido. */
export type GrowthSummary = z.infer<typeof growthSummarySchema>;
