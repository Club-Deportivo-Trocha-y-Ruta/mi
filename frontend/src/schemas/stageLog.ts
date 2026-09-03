import { z } from "zod";

/**
 * Schemas de validación de la Bitácora (StageLog), feature 038.
 *
 * Mirror 1:1 de `frontend/src/types/stageLog.types.ts` /
 * `backend/app/services/training/stage_log.py`. Usados para `.parse()`
 * las respuestas de API en tests y MSW (`.strip()` = allowlist en cliente).
 */

// ---------------------------------------------------------------------------
// Enums
// ---------------------------------------------------------------------------

export const waypointKindSchema = z.enum([
  "first_session",
  "race",
  "streak",
  "badge",
  "best_session",
  "next_race",
]);

export const blockStateSchema = z.enum([
  "ai",
  "edited",
  "static",
  "hidden",
  "empty",
]);

export const summitKindSchema = z.enum(["race", "training"]);

export const stageLogConfidenceSchema = z.enum(["low", "medium", "high"]);

export const stageBlockRefSchema = z.enum([
  "attendance",
  "technical",
  "race",
  "badges",
  "streak",
]);

export const regenerableBlockSchema = z.enum([
  "stage_title",
  "summit_caption",
  "observations",
  "next_segment_text",
  "family_compass",
  "analyst_reading",
]);

export const hideableBlockSchema = z.enum([
  "analyst_reading",
  "photos",
  "badges",
  "coach_note",
]);

// ---------------------------------------------------------------------------
// Sub-modelos
// ---------------------------------------------------------------------------

export const waypointSchema = z
  .object({
    kind: waypointKindSchema,
    date: z.string(),
    label: z.string(),
    sublabel: z.string().nullable(),
    icon: z.string(),
    is_future: z.boolean(),
  })
  .strip();

export const effortWeekSchema = z
  .object({
    week_label: z.string(),
    sessions_planned: z.number(),
    sessions_attended: z.number(),
    mean_rpe: z.number().nullable(),
  })
  .strip();

export const summitSchema = z
  .object({
    kind: summitKindSchema,
    title: z.string(),
    detail: z.string().nullable(),
    caption: z.string().nullable(),
    date: z.string().nullable(),
  })
  .strip();

export const observationSchema = z
  .object({
    claim: z.string(),
    evidence: z.string(),
    block_ref: stageBlockRefSchema,
  })
  .strip();

export const analystReadingSchema = z
  .object({
    headline_family: z.string(),
    action_family: z.string(),
    valida_label: z.string(),
    source_insight_id: z.number(),
  })
  .strip();

export const nextRaceSchema = z
  .object({
    label: z.string(),
    date: z.string(),
    venue: z.string().nullable(),
    priority_label: z.string().nullable(),
  })
  .strip();

export const nextSegmentSchema = z
  .object({
    focus_groups: z.array(z.string()),
    next_race: nextRaceSchema.nullable(),
    text: z.string().nullable(),
  })
  .strip();

export const familyCompassSchema = z
  .object({
    conversation_question: z.string(),
    monthly_challenge: z.string(),
    what_to_watch: z.string(),
  })
  .strip();

export const badgeViewSchema = z
  .object({
    code: z.string(),
    label: z.string(),
    icon: z.string(),
    earned_at: z.string().nullable(),
  })
  .strip();

export const photoViewSchema = z
  .object({
    thumbnail_url: z.string(),
    caption: z.string().nullable(),
  })
  .strip();

// ---------------------------------------------------------------------------
// StageLog (raíz) — DTO coach
// ---------------------------------------------------------------------------

export const stageLogSchema = z
  .object({
    schema_version: z.literal(2),
    stage_number: z.number(),
    period_label: z.string(),
    is_current_month: z.boolean(),
    athlete_first_name: z.string(),
    athlete_reference: z.string(),
    stage_title: z.string(),
    trail: z.array(waypointSchema),
    summit: summitSchema.nullable(),
    observations: z.array(observationSchema),
    analyst_reading: analystReadingSchema.nullable(),
    effort_profile: z.array(effortWeekSchema),
    next_segment: nextSegmentSchema.nullable(),
    family_compass: familyCompassSchema.nullable(),
    badges: z.array(badgeViewSchema),
    photos: z.array(photoViewSchema),
    coach_note: z.string().nullable(),
    block_states: z.record(z.string(), blockStateSchema),
    grounding_violations: z.array(z.string()),
  })
  .strip();

// ---------------------------------------------------------------------------
// ParentStageLog — DTO padre (to_parent_dto): sin block_states,
// grounding_violations ni analyst_reading.source_insight_id
// ---------------------------------------------------------------------------

export const analystReadingTextSchema = z
  .object({
    headline_family: z.string(),
    action_family: z.string(),
  })
  .strip();

/** `analyst_reading` en el DTO padre: igual a `AnalystReading` sin `source_insight_id`. */
export const parentAnalystReadingSchema = z
  .object({
    headline_family: z.string(),
    action_family: z.string(),
    valida_label: z.string(),
  })
  .strip();

export const parentStageLogSchema = z
  .object({
    schema_version: z.literal(2),
    stage_number: z.number(),
    period_label: z.string(),
    is_current_month: z.boolean(),
    athlete_first_name: z.string(),
    athlete_reference: z.string(),
    stage_title: z.string(),
    trail: z.array(waypointSchema),
    summit: summitSchema.nullable(),
    observations: z.array(observationSchema),
    analyst_reading: parentAnalystReadingSchema.nullable(),
    effort_profile: z.array(effortWeekSchema),
    next_segment: nextSegmentSchema.nullable(),
    family_compass: familyCompassSchema.nullable(),
    badges: z.array(badgeViewSchema),
    photos: z.array(photoViewSchema),
    coach_note: z.string().nullable(),
  })
  .strip();

// ---------------------------------------------------------------------------
// StageNarrative — salida del LLM (ai_narrative v2)
// ---------------------------------------------------------------------------

export const stageNarrativeSchema = z
  .object({
    stage_title: z.string(),
    summit_caption: z.string().nullable(),
    observations: z.array(observationSchema),
    next_segment_text: z.string().nullable(),
    family_compass: familyCompassSchema,
    analyst_reading: analystReadingTextSchema.nullable(),
    model: z.string(),
    prompt_version: z.string(),
    confidence: stageLogConfidenceSchema,
  })
  .strip();

// ---------------------------------------------------------------------------
// StageOverrides — payload de PATCH / preview local del estudio
// ---------------------------------------------------------------------------

export const stageOverridesSchema = z
  .object({
    stage_title: z.string().optional(),
    summit_caption: z.string().optional(),
    observations: z.array(observationSchema).optional(),
    analyst_reading: analystReadingTextSchema.optional(),
    next_segment_text: z.string().optional(),
    family_compass: familyCompassSchema.optional(),
  })
  .strip();
