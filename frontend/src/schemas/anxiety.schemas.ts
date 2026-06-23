import { z } from "zod";

/** Schemas de validación de respuestas del backend de ansiedad (feature 017).
 *
 * Defensa en profundidad: `.strip()` descarta cualquier campo no declarado
 * (allowlist en cliente) — relevante para datos de menores.
 */

const instrumentType = z.enum(["csai2", "csai2r", "sas2"]);
const status = z.enum(["pending", "partial", "completed"]);
const source = z.enum(["llm", "rule"]);

export const issuedTokenSchema = z
  .object({ token: z.string(), expires_at: z.string() })
  .strip();

export const assessmentCreatedSchema = z
  .object({
    id: z.number(),
    athlete_id: z.number(),
    instrument_type: instrumentType,
    status,
    instrument_override: z.boolean(),
    scheduled_at: z.string(),
    warning: z.string().nullable(),
    token: issuedTokenSchema.nullable(),
  })
  .strip();

export const batchCreatedSchema = z
  .object({
    items: z.array(
      z
        .object({
          athlete_id: z.number(),
          created: z.boolean(),
          assessment: assessmentCreatedSchema.nullable(),
          warning: z.string().nullable(),
          error: z.string().nullable(),
        })
        .strip(),
    ),
  })
  .strip();

export const answerFormSchema = z
  .object({
    instrument_type: instrumentType,
    intro: z.string(),
    scale_min: z.number(),
    scale_max: z.number(),
    items: z.array(
      z.object({ item_id: z.number(), text: z.string().nullable() }).strip(),
    ),
  })
  .strip();

export const answerResultSchema = z
  .object({
    status: z.enum(["completed", "partial"]),
    short_message: z.string(),
  })
  .strip();

const subscaleRead = z
  .object({
    score: z.number().nullable(),
    baseline: z.number().nullable(),
    delta: z.number().nullable(),
  })
  .strip();

export const interpretationSchema = z
  .object({
    resumen: z.string(),
    por_dimension: z
      .object({
        cognitiva: z.string(),
        somatica: z.string(),
        autoconfianza: z.string(),
      })
      .strip(),
    estrategias: z.array(z.string()),
    mensaje_para_el_atleta: z.string(),
    banderas: z.array(z.string()),
  })
  .strip();

export const assessmentReadSchema = z
  .object({
    id: z.number(),
    athlete_id: z.number(),
    instrument_type: instrumentType,
    event_id: z.number().nullable(),
    priority: z.enum(["A", "B", "C"]).nullable(),
    scheduled_at: z.string(),
    status,
    is_partial: z.boolean(),
    instrument_override: z.boolean(),
    cognitive: subscaleRead,
    somatic: subscaleRead,
    selfconfidence: subscaleRead,
    interpretation: interpretationSchema.nullable(),
    interpretation_source: source.nullable(),
    flags: z.array(z.string()),
  })
  .strip();

export const interpretationResponseSchema = z
  .object({
    assessment_id: z.number(),
    interpretation: interpretationSchema,
    source,
    model: z.string().nullable(),
  })
  .strip();

const seriesPoint = z
  .object({
    assessment_id: z.number(),
    scheduled_at: z.string(),
    event_id: z.number().nullable(),
    cognitive: z.number().nullable(),
    somatic: z.number().nullable(),
    selfconfidence: z.number().nullable(),
    flags: z.array(z.string()),
  })
  .strip();

export const athleteSeriesSchema = z
  .object({
    athlete_id: z.number(),
    instrument_type: instrumentType,
    baseline_cognitive: z.number().nullable(),
    baseline_somatic: z.number().nullable(),
    baseline_selfconfidence: z.number().nullable(),
    points: z.array(seriesPoint),
    note: z.string().nullable(),
  })
  .strip();

const groupMember = z
  .object({
    athlete_id: z.number(),
    assessment_id: z.number(),
    cognitive: z.number().nullable(),
    somatic: z.number().nullable(),
    selfconfidence: z.number().nullable(),
    flags: z.array(z.string()),
  })
  .strip();

export const groupTriageSchema = z
  .object({
    event_id: z.number(),
    buckets: z.object({
      somatic_high: z.array(groupMember),
      cognitive_high: z.array(groupMember),
      confidence_low: z.array(groupMember),
      favorable: z.array(groupMember),
    }),
    alerts: z.array(groupMember),
  })
  .strip();

export const importResultSchema = z
  .object({
    imported: z.number(),
    skipped: z.number(),
    errors: z.array(
      z.object({ row: z.number(), error: z.string() }).strip(),
    ),
  })
  .strip();
