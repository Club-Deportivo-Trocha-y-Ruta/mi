/**
 * Tipos del módulo Entrenamiento por Intervalos (feature 026).
 *
 * Superficie pública de tipos consumida por `api/intervals.ts`, los hooks y los
 * componentes. Se infieren de los schemas Zod (`schemas/intervals.schema.ts`),
 * que son la fuente única de verdad de las formas de datos (contracts/api.md).
 */

import type { z } from "zod";

import type {
  blockMatchStatusSchema,
  hrZoneSchema,
  instructivoBrandSchema,
  intervalAgeBandSchema,
  intervalAttachInputSchema,
  intervalBlockInputSchema,
  intervalBlockOutSchema,
  intervalBlockTypeSchema,
  intervalRecalculateInputSchema,
  intervalStructureCreateInputSchema,
  intervalStructureOutSchema,
  intervalStructureUpdateInputSchema,
  intervalTemplateFiltersSchema,
  intervalTemplateListSchema,
  intervalTemplateOutSchema,
  intervalTemplateSaveInputSchema,
  matchBlockSchema,
  matchDetailSchema,
  matchExtraLapSchema,
  matchOverallStatusSchema,
  matchRecalculateResponseSchema,
  matchSummarySchema,
  matchTriggerSchema,
} from "@/schemas/intervals.schema";

// ---------------------------------------------------------------------------
// Enums / uniones
// ---------------------------------------------------------------------------

export type IntervalAgeBand = z.infer<typeof intervalAgeBandSchema>;
export type IntervalBlockType = z.infer<typeof intervalBlockTypeSchema>;
export type HrZone = z.infer<typeof hrZoneSchema>;
export type MatchOverallStatus = z.infer<typeof matchOverallStatusSchema>;
export type BlockMatchStatus = z.infer<typeof blockMatchStatusSchema>;
export type MatchTrigger = z.infer<typeof matchTriggerSchema>;
export type InstructivoBrand = z.infer<typeof instructivoBrandSchema>;

// ---------------------------------------------------------------------------
// Entradas (formularios / payloads de request)
// ---------------------------------------------------------------------------

export type IntervalBlockInput = z.infer<typeof intervalBlockInputSchema>;
export type IntervalStructureCreateInput = z.infer<
  typeof intervalStructureCreateInputSchema
>;
export type IntervalStructureUpdateInput = z.infer<
  typeof intervalStructureUpdateInputSchema
>;
export type IntervalTemplateSaveInput = z.infer<
  typeof intervalTemplateSaveInputSchema
>;
export type IntervalTemplateFilters = z.infer<
  typeof intervalTemplateFiltersSchema
>;
export type IntervalAttachInput = z.infer<typeof intervalAttachInputSchema>;
export type IntervalRecalculateInput = z.infer<
  typeof intervalRecalculateInputSchema
>;

// ---------------------------------------------------------------------------
// Respuestas del servidor
// ---------------------------------------------------------------------------

export type IntervalBlockOut = z.infer<typeof intervalBlockOutSchema>;
export type IntervalStructureOut = z.infer<typeof intervalStructureOutSchema>;
export type IntervalTemplateOut = z.infer<typeof intervalTemplateOutSchema>;
export type IntervalTemplateList = z.infer<typeof intervalTemplateListSchema>;
export type MatchBlock = z.infer<typeof matchBlockSchema>;
export type MatchExtraLap = z.infer<typeof matchExtraLapSchema>;
export type MatchSummary = z.infer<typeof matchSummarySchema>;
export type MatchDetail = z.infer<typeof matchDetailSchema>;
export type MatchRecalculateResponse = z.infer<
  typeof matchRecalculateResponseSchema
>;

// ---------------------------------------------------------------------------
// Manejo de errores (mapeo HTTP → UI)
// ---------------------------------------------------------------------------

export type IntervalErrorKind =
  | "not_found"
  | "conflict"
  | "forbidden"
  | "unauthorized"
  | "validation"
  | "rate_limited"
  | "cancelled"
  | "unknown";

export interface IntervalErrorInfo {
  kind: IntervalErrorKind;
  message: string;
}

/** Códigos 422 legibles por máquina que devuelve el backend (contracts/api.md). */
export type IntervalValidationCode =
  | "cadence_below_minimum"
  | "age_gate_z3_blocked"
  | "age_gate_confirmation_required"
  | "invalid_repeat_group";

export interface IntervalValidationError {
  code: IntervalValidationCode;
  message: string;
  /** Posiciones de bloque implicadas (cuando el backend las reporta). */
  positions?: number[];
}

/** Info del guardrail de categoría confirmable (FR-007) — abre `AgeGateDialog`. */
export interface AgeGateError {
  /** Explicación en español devuelta por el backend. */
  message: string;
}
