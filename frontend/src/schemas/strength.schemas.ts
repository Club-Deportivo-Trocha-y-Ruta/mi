/**
 * Schemas de validación del módulo Fuerza y Acondicionamiento (feature 021).
 *
 * Política de `.strip()`: descarta campos no declarados (allowlist en cliente).
 * Todos los schemas de respuesta del servidor se usan para `.parse()` en api/strength.ts.
 * Los schemas de formulario se usan con zodResolver en los componentes (tareas posteriores).
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Enums compartidos
// ---------------------------------------------------------------------------

/** AgeBand reutilizado de 018 (`7-9`/`10-12`/`13-15`); 021 seeds/UI solo usan `10-12`/`13-15`. */
export const strengthAgeBandSchema = z.enum(["10-12", "13-15"]);
export const equipmentKindSchema = z.enum(["sin_equipo", "equipo_gym"]);
export const movementCategorySchema = z.enum([
  "empuje_superior",
  "traccion_superior",
  "inferior_bilateral",
  "inferior_unilateral",
  "core_estabilidad",
]);
export const strengthProgressStatusSchema = z.enum([
  "introducido",
  "en_progreso",
  "dominado",
]);

// ---------------------------------------------------------------------------
// Catalog — server response schemas (US1)
// ---------------------------------------------------------------------------

export const strengthExerciseListItemSchema = z
  .object({
    id: z.number(),
    slug: z.string(),
    name: z.string(),
    summary: z.string(),
    equipment: equipmentKindSchema,
    equipment_detail: z.string().nullable(),
    movement_category: movementCategorySchema,
    age_bands: z.array(strengthAgeBandSchema),
    suggested_duration_min: z.number(),
    suggested_reps: z.string(),
    is_seeded: z.boolean(),
    is_hidden: z.boolean(),
  })
  .strip();

export const strengthCatalogListSchema = z
  .object({
    items: z.array(strengthExerciseListItemSchema),
    total: z.number(),
  })
  .strip();

export const strengthExerciseDetailSchema = strengthExerciseListItemSchema
  .extend({
    how_to: z.string(),
    common_errors: z.string().nullable(),
    illustration_ascii: z.string().nullable(),
    illustration_alt: z.string().nullable(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Catalog — filter/query params (client-side, used to build request params)
// ---------------------------------------------------------------------------

export const strengthCatalogFiltersSchema = z
  .object({
    q: z.string().optional(),
    equipment: equipmentKindSchema.optional(),
    age_band: strengthAgeBandSchema.optional(),
    movement_category: movementCategorySchema.optional(),
    include_hidden: z.boolean().optional(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Blocks — server response schemas (US2)
// ---------------------------------------------------------------------------

export const strengthEntryOutSchema = z
  .object({
    id: z.number(),
    position: z.number(),
    duration_min: z.number(),
    reps: z.string().nullable(),
    is_age_override: z.boolean(),
    override_note: z.string().nullable(),
    exercise: strengthExerciseListItemSchema,
  })
  .strip();

export const strengthBlockOutSchema = z
  .object({
    id: z.number(),
    name: z.string(),
    target_age_band: strengthAgeBandSchema,
    duration_target_min: z.number(),
    total_duration_min: z.number(),
    is_archived: z.boolean(),
    entries: z.array(strengthEntryOutSchema),
    created_at: z.string(),
  })
  .strip();

export const strengthBlockListSchema = z
  .object({
    items: z.array(strengthBlockOutSchema),
    total: z.number(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Blocks — request payload schemas (US2)
// ---------------------------------------------------------------------------

export const strengthBlockEntryInSchema = z.object({
  exercise_id: z.number(),
  position: z.number().min(0),
  duration_min: z.number().gt(0),
  reps: z.string().max(60).optional(),
  is_age_override: z.boolean().default(false),
  override_note: z.string().max(300).optional(),
});

export const strengthBlockSaveInputSchema = z.object({
  name: z.string().max(120),
  target_age_band: strengthAgeBandSchema,
  duration_target_min: z.number().gt(0).default(30),
  entries: z.array(strengthBlockEntryInSchema).min(1),
});

export const strengthBlockListFiltersSchema = z
  .object({
    include_archived: z.boolean().optional(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Session attachment — schemas (US2)
// ---------------------------------------------------------------------------

export const strengthAttachOutSchema = z
  .object({
    id: z.number(),
    training_session_id: z.number(),
    block_id: z.number(),
    position: z.number(),
    attached_at: z.string(),
  })
  .strip();

export const strengthSessionBlocksSchema = z
  .object({
    items: z.array(strengthBlockOutSchema),
  })
  .strip();

// ---------------------------------------------------------------------------
// Per-athlete progress notes — server response schemas (US4)
// ---------------------------------------------------------------------------

export const strengthProgressOutSchema = z
  .object({
    exercise_id: z.number(),
    exercise_name: z.string(),
    status: strengthProgressStatusSchema,
    coach_note: z.string().nullable(),
    season: z.number(),
    recorded_at: z.string(),
  })
  .strip();

export const strengthAthleteProgressSchema = z
  .object({
    items: z.array(strengthProgressOutSchema),
  })
  .strip();

// ---------------------------------------------------------------------------
// Per-athlete progress notes — request payload schema (US4)
// ---------------------------------------------------------------------------

export const strengthProgressInSchema = z
  .object({
    exercise_id: z.number().int().positive("Selecciona un ejercicio."),
    status: strengthProgressStatusSchema,
    coach_note: z.string().max(500, "Máximo 500 caracteres.").optional(),
    season: z
      .number({ error: "El año de temporada es obligatorio." })
      .int()
      .min(2020)
      .max(2100),
  })
  .strip();

// ---------------------------------------------------------------------------
// Inferred types (convenience re-exports for api.ts / hooks / components)
// ---------------------------------------------------------------------------

export type StrengthAgeBand = z.infer<typeof strengthAgeBandSchema>;
export type EquipmentKind = z.infer<typeof equipmentKindSchema>;
export type MovementCategory = z.infer<typeof movementCategorySchema>;
export type StrengthProgressStatus = z.infer<
  typeof strengthProgressStatusSchema
>;
export type StrengthExerciseListItem = z.infer<
  typeof strengthExerciseListItemSchema
>;
export type StrengthCatalogList = z.infer<typeof strengthCatalogListSchema>;
export type StrengthExerciseDetail = z.infer<
  typeof strengthExerciseDetailSchema
>;
export type StrengthCatalogFilters = z.infer<
  typeof strengthCatalogFiltersSchema
>;
export type StrengthEntryOut = z.infer<typeof strengthEntryOutSchema>;
export type StrengthBlockOut = z.infer<typeof strengthBlockOutSchema>;
export type StrengthBlockList = z.infer<typeof strengthBlockListSchema>;
export type StrengthBlockEntryInput = z.infer<
  typeof strengthBlockEntryInSchema
>;
export type StrengthBlockSaveInput = z.infer<
  typeof strengthBlockSaveInputSchema
>;
export type StrengthBlockListFilters = z.infer<
  typeof strengthBlockListFiltersSchema
>;
export type StrengthAttachOut = z.infer<typeof strengthAttachOutSchema>;
export type StrengthSessionBlocks = z.infer<
  typeof strengthSessionBlocksSchema
>;
export type StrengthProgressOut = z.infer<typeof strengthProgressOutSchema>;
export type StrengthAthleteProgress = z.infer<
  typeof strengthAthleteProgressSchema
>;
export type StrengthProgressInput = z.infer<typeof strengthProgressInSchema>;
