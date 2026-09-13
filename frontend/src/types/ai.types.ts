import type { z } from "zod";

import type {
  anthropometricRecordExplanationResponseSchema,
  anthropometryInsightOutSchema,
  anthropometryInsightV1Schema,
  confidenceLevelSchema,
  confidenceSchema,
  criticVerdictSchema,
  phvExplanationResponseSchema,
} from "@/schemas/ai.schemas";

/** Grupo de edad usado por el backend para ajustar guardrails. */
export type AgeGroup = "10-12" | "13-15" | "16+";

// ---------------------------------------------------------------------------
// AnthropometryInsightV1 (feature 042) — inferidos de `schemas/ai.schemas.ts`,
// que es la fuente única de verdad de estas formas (contracts/insight-schema.md,
// contracts/measurement-analysis-api.md). Mismo patrón que
// `types/growth.types.ts` / `types/intervals.types.ts`.
// ---------------------------------------------------------------------------

/** Nivel de confianza del análisis estructurado ("high" | "medium" | "low"). */
export type ConfidenceLevel = z.infer<typeof confidenceLevelSchema>;

/** `{ level, reason }` — nunca se traduce, `reason` ya viene en español. */
export type Confidence = z.infer<typeof confidenceSchema>;

/** Payload interno del análisis estructurado (versión de PAYLOAD, siempre
 *  "v1" hoy — distinto del `schema_version` de FORMATO DE FILA de abajo). */
export type AnthropometryInsightV1 = z.infer<typeof anthropometryInsightV1Schema>;

/** Subconjunto de `AnthropometryInsightV1` que viaja como `structured` en la
 *  respuesta del endpoint (sin `schema_version`/`audience`/`word_count`). */
export type AnthropometryInsightOut = z.infer<typeof anthropometryInsightOutSchema>;

/** Veredicto persistido de cinco valores (`critic_verdict`, data-model.md §3). */
export type CriticVerdict = z.infer<typeof criticVerdictSchema>;

/**
 * Respuesta de POST/GET /api/ai/athletes/{id}/phv-explanation.
 *
 * Unión discriminada sobre `schema_version` (FORMATO DE FILA, "v1" | "v2",
 * default "v1" cuando el backend lo omite — fila legacy pre-042): una fila
 * "v1" trae `structured`/`critic_verdict`/`prompt_version`/`trace_id` en
 * `null`; una fila "v2" siempre trae `structured` y `critic_verdict`
 * poblados. `text`, `model`, `provider`, `generated_at`, `age_group` y
 * `maturation_status` no cambian de nombre ni de significado entre
 * versiones — se pueden leer sin distinguir la rama.
 */
export type PHVExplanationResponse = z.infer<typeof phvExplanationResponseSchema>;

/** Respuesta de GET /api/ai/health (solo admin). */
export interface AIHealthResponse {
  enabled: boolean;
  provider: string;
  model: string;
}

/** Estado de presupuesto de IA para la señal pre-lanzamiento. */
export type AIBudgetStatus = "ok" | "warning" | "exhausted";

/** Respuesta de GET /api/ai/status (coach + admin).
 *
 * Señal pre-lanzamiento reutilizada por todo botón "Analizar con IA"
 * para mostrar presupuesto/concurrencia antes del clic. Sin montos en
 * dólares (eso sigue siendo solo-admin vía /admin/ai-usage) ni
 * identificadores de deportistas.
 */
export interface AIStatusResponse {
  budget_status: AIBudgetStatus;
  budget_remaining_pct: number;
  concurrency_available: boolean;
  est_wait_seconds: number;
}

/** Respuesta de POST/GET
 *  /api/ai/athletes/{id}/measurements/{record_id}/explanation
 *
 *  Análisis particular de una medición vs el historial. A diferencia del
 *  PHV global, incluye los deltas calculados respecto a la medición
 *  inmediata anterior para que el frontend pueda renderizar un resumen
 *  visual antes del texto IA.
 */
export type AnthropometricRecordExplanationResponse = z.infer<
  typeof anthropometricRecordExplanationResponseSchema
>;
