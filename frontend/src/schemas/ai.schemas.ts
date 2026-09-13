import { z } from "zod";

import { MaturationStatus } from "@/types/enums";

/** Schema de validación de la respuesta del backend.
 *
 * Defensa en profundidad: si el backend filtrara accidentalmente PII
 * (first_name, last_name, birth_date…) Zod las descarta porque no están
 * declaradas. Equivale a una allowlist en cliente.
 */

export const aiHealthResponseSchema = z
  .object({
    enabled: z.boolean(),
    provider: z.string(),
    model: z.string(),
  })
  .strip();

export const aiStatusResponseSchema = z
  .object({
    budget_status: z.enum(["ok", "warning", "exhausted"]),
    budget_remaining_pct: z.number(),
    concurrency_available: z.boolean(),
    est_wait_seconds: z.number(),
  })
  .strip();

// ---------------------------------------------------------------------------
// AnthropometryInsightV1 (feature 042) — mirror de
// backend/app/services/ai/anthro/schemas.py::AnthropometryInsightV1
// (contracts/insight-schema.md §1/§2, verbatim).
//
// OJO: el `schema_version` de este objeto es la versión del PAYLOAD del
// análisis interno (hoy siempre "v1" — no existe todavía un v2 de este
// payload). Es un eje distinto del `schema_version` de FORMATO DE FILA que
// discrimina la respuesta del endpoint más abajo (data-model.md §0) — no
// confundir los dos.
// ---------------------------------------------------------------------------

export const confidenceLevelSchema = z.enum(["high", "medium", "low"]);

export const confidenceSchema = z
  .object({
    level: confidenceLevelSchema,
    reason: z.string().min(3).max(200),
  })
  .strip();

export const anthropometryInsightV1Schema = z
  .object({
    schema_version: z.literal("v1"),
    audience: z.enum(["family", "coach"]),
    summary_line: z.string().min(3).max(140),
    changes: z.array(z.string()).min(1).max(4),
    meaning: z.array(z.string()).min(1).max(4),
    next_weeks: z.array(z.string()).min(1).max(3),
    warning_signs: z.array(z.string()).max(2),
    confidence: confidenceSchema,
    data_gaps: z.array(z.string()).max(3),
    word_count: z.number().int().nonnegative(),
  })
  .strip();

/**
 * Subconjunto de `AnthropometryInsightV1` que viaja como `structured` en la
 * respuesta del endpoint (`AnthropometryInsightOut`,
 * measurement-analysis-api.md §2): mismas cardinalidades y el mismo tope de
 * 140 caracteres en `summary_line`, sin los campos internos
 * `schema_version`/`audience`/`word_count`. Se mantiene como schema separado
 * a propósito — si el schema interno del analista gana un campo nuevo, el
 * contrato de cable no cambia de forma silenciosa.
 */
export const anthropometryInsightOutSchema = z
  .object({
    summary_line: z.string().min(3).max(140),
    changes: z.array(z.string()).min(1).max(4),
    meaning: z.array(z.string()).min(1).max(4),
    next_weeks: z.array(z.string()).min(1).max(3),
    warning_signs: z.array(z.string()).max(2),
    confidence: confidenceSchema,
    data_gaps: z.array(z.string()).max(3),
  })
  .strip();

/**
 * Veredicto PERSISTIDO (formato de fila, cinco valores —
 * data-model.md §3). Distinto del vocabulario crudo de tres valores del
 * crítico interno (`AnthropometryCriticVerdict.verdict`), que el frontend
 * nunca recibe — la API solo expone este.
 */
export const criticVerdictSchema = z.enum([
  "approved",
  "revised",
  "flagged",
  "fallback",
  "skipped",
]);

// ---------------------------------------------------------------------------
// Unión discriminada de FORMATO DE FILA (v1 | v2) sobre `schema_version` —
// measurement-analysis-api.md §2. Comparten estos campos, sin cambio de
// nombre ni de significado entre versiones (contrato explícito):
//   text, model, provider, generated_at, age_group, maturation_status
// y, en el endpoint de medición puntual, además:
//   record_id, num_previous_measurements, delta_height_cm, delta_weight_kg
//
// Si el backend omite `schema_version` (fila legacy pre-042) se normaliza a
// "v1" ANTES de validar, así una fila legacy nunca falla el parseo y sigue
// renderizando para siempre (FR-026) — el default vive en el propio schema,
// no en cada call site, por lo que es imposible olvidarlo al consumir esto.
// ---------------------------------------------------------------------------

/** Inserta `schema_version: "v1"` cuando el campo viene ausente o `null`
 *  (payload pre-042, sin los cuatro campos nuevos). No toca el valor si ya
 *  viene poblado ("v1" explícito o "v2"). */
function defaultRowSchemaVersion(value: unknown): unknown {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    const record = value as Record<string, unknown>;
    if (record.schema_version === undefined || record.schema_version === null) {
      return { ...record, schema_version: "v1" };
    }
  }
  return value;
}

const explanationBaseShape = {
  text: z.string().min(1),
  model: z.string(),
  provider: z.string(),
  generated_at: z.string(),
  age_group: z.enum(["10-12", "13-15", "16+"]),
  maturation_status: z.union([z.nativeEnum(MaturationStatus), z.literal("")]),
};

// Los cuatro campos añadidos por 042 en la rama v1: siempre ausentes o
// `null` en una fila legacy — se aceptan ausentes (`.optional()`) además de
// `null` porque un payload pre-042 real nunca los incluye en absoluto.
const v1RowAdditionsShape = {
  structured: z.null().optional(),
  critic_verdict: z.null().optional(),
  is_fallback: z.boolean().optional(),
  prompt_version: z.null().optional(),
  trace_id: z.null().optional(),
};

// La rama v2: `structured` y `critic_verdict` SIEMPRE poblados (el backend
// solo marca una fila como v2 tras correr el pipeline nuevo). Un
// `structured` corrupto (no cumple `anthropometryInsightOutSchema`) hace
// fallar el parseo de esta rama del union — no lanza una excepción genérica
// no capturable — así el caller puede usar `.safeParse()` y degradar a un
// mensaje de error en la tarjeta en vez de reventar el error boundary.
// `prompt_version`/`trace_id` quedan opcionales/nulos: son técnicos y
// solo-coach (measurement-analysis-api.md §4), una respuesta de familia o
// una corrida sin traza los omite o los manda en `null`.
const v2RowAdditionsShape = {
  structured: anthropometryInsightOutSchema,
  critic_verdict: criticVerdictSchema,
  is_fallback: z.boolean().default(false),
  prompt_version: z.string().nullable().optional(),
  trace_id: z.string().nullable().optional(),
};

const phvExplanationV1Schema = z
  .object({
    ...explanationBaseShape,
    schema_version: z.literal("v1"),
    ...v1RowAdditionsShape,
  })
  .strip();

const phvExplanationV2Schema = z
  .object({
    ...explanationBaseShape,
    schema_version: z.literal("v2"),
    ...v2RowAdditionsShape,
  })
  .strip();

export const phvExplanationResponseSchema = z.preprocess(
  defaultRowSchemaVersion,
  z.discriminatedUnion("schema_version", [
    phvExplanationV1Schema,
    phvExplanationV2Schema,
  ]),
);

const recordExplanationExtraShape = {
  record_id: z.number().int(),
  num_previous_measurements: z.number().int().nonnegative(),
  delta_height_cm: z.number().nullable(),
  delta_weight_kg: z.number().nullable(),
};

const anthropometricRecordExplanationV1Schema = z
  .object({
    ...explanationBaseShape,
    ...recordExplanationExtraShape,
    schema_version: z.literal("v1"),
    ...v1RowAdditionsShape,
  })
  .strip();

const anthropometricRecordExplanationV2Schema = z
  .object({
    ...explanationBaseShape,
    ...recordExplanationExtraShape,
    schema_version: z.literal("v2"),
    ...v2RowAdditionsShape,
  })
  .strip();

export const anthropometricRecordExplanationResponseSchema = z.preprocess(
  defaultRowSchemaVersion,
  z.discriminatedUnion("schema_version", [
    anthropometricRecordExplanationV1Schema,
    anthropometricRecordExplanationV2Schema,
  ]),
);

export type PHVExplanationResponseValidated = z.infer<
  typeof phvExplanationResponseSchema
>;

export type AnthropometricRecordExplanationResponseValidated = z.infer<
  typeof anthropometricRecordExplanationResponseSchema
>;
