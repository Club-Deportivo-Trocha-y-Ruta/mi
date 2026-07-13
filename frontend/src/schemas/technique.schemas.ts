import { z } from "zod";

/**
 * Schemas de validación del módulo Técnica y Gymkhana (feature 018).
 *
 * Política de `.strip()`: descarta campos no declarados (allowlist en cliente).
 * Todos los schemas de respuesta del servidor se usan para `.parse()` en api/technique.ts.
 * Los schemas de formulario se usan con zodResolver en los componentes.
 */

// ---------------------------------------------------------------------------
// Enums compartidos
// ---------------------------------------------------------------------------

export const ageBandSchema = z.enum(["7-9", "10-12", "13-15"]);
export const difficultySchema = z.enum(["facil", "media", "avanzada"]);
export const sessionSegmentSchema = z.enum([
  "calentamiento",
  "principal",
  "vuelta_calma",
]);
export const skillProgressStatusSchema = z.enum([
  "introducido",
  "en_progreso",
  "dominado",
]);

// ---------------------------------------------------------------------------
// Taxonomy — server response schemas
// ---------------------------------------------------------------------------

export const skillRefSchema = z
  .object({
    code: z.string(),
    slug: z.string(),
    name: z.string(),
  })
  .strip();

export const skillSchema = skillRefSchema
  .extend({ order: z.number().nullable().optional() })
  .strip();

export const materialSchema = z
  .object({
    slug: z.string(),
    name: z.string(),
    is_none: z.boolean(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Catalog — server response schemas
// ---------------------------------------------------------------------------

export const exerciseListItemSchema = z
  .object({
    id: z.number(),
    slug: z.string(),
    name: z.string(),
    summary: z.string(),
    difficulty: difficultySchema,
    is_game: z.boolean(),
    is_gymkhana: z.boolean(),
    age_bands: z.array(ageBandSchema),
    skills: z.array(skillRefSchema),
    materials: z.array(materialSchema),
    is_seeded: z.boolean(),
    is_hidden: z.boolean(),
  })
  .strip();

export const catalogListSchema = z
  .object({
    items: z.array(exerciseListItemSchema),
    total: z.number(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Circuit diagrams — feature 019 (Phase A)
// ---------------------------------------------------------------------------

/**
 * Controlled vocabulary for circuit element kinds.
 * Phase A: no free-text label — elements are identified by kind + optional #n.
 */
export const circuitElementKindSchema = z.enum([
  "cone",
  "line",
  "gate",
  "mine",
  "arrow",
  "beam",
  "ring",
]);

/**
 * One element placed on the canvas.
 * - `style` is semantically meaningful only for `kind = 'line'`; it is accepted
 *   (and ignored) on other kinds so the server strip-on-write rule is not
 *   mirrored client-side as a hard error.
 * - `label` is intentionally ABSENT — Phase A enforces the controlled set only
 *   (FR-023 / O-5). `.strip()` will remove any `label` that arrives from a
 *   server response or an untrusted source. The Phase A guard test must keep
 *   passing (O-6: "never by loosening the Phase A guard").
 *   Phase B uses circuitElementSchemaPhaseB (below) — a SEPARATE schema.
 * - Coordinate finiteness and canvas-bounds are enforced at the layout level
 *   (gymkhanaLayoutSchema.superRefine) because those checks require width/height.
 */
export const circuitElementSchema = z
  .object({
    kind: circuitElementKindSchema,
    x: z.number(),
    y: z.number(),
    // The backend (Pydantic) serializes absent optional fields as explicit
    // `null`, not omitted — accept `null | undefined` on input, then normalize
    // `null → undefined` so the parsed type stays `number | undefined` and
    // matches the canonical CircuitElement TS type.
    rotation: z
      .number()
      .nullish()
      .transform((v) => v ?? undefined),
    // dashed = guía/libre path; solid = trayecto técnico (precision)
    style: z
      .enum(["dashed", "solid"])
      .nullish()
      .transform((v) => v ?? undefined),
  })
  .strip();

/**
 * Complete layout document stored in `technique_exercises.layout_json`.
 *
 * Invariants enforced here (mirrors Pydantic FR-007):
 *   width > 0, height > 0, both finite.
 *   Per element: x/y/rotation finite; 0 ≤ x ≤ width; 0 ≤ y ≤ height.
 *   Empty `elements` array is valid.
 */
export const gymkhanaLayoutSchema = z
  .object({
    width: z.number().positive(),
    height: z.number().positive(),
    elements: z.array(circuitElementSchema),
  })
  .strip()
  .superRefine((data, ctx) => {
    if (!Number.isFinite(data.width)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["width"],
        message: "El ancho debe ser un número finito.",
      });
    }
    if (!Number.isFinite(data.height)) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["height"],
        message: "El alto debe ser un número finito.",
      });
    }
    data.elements.forEach((el, i) => {
      if (!Number.isFinite(el.x)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["elements", i, "x"],
          message: "La coordenada x debe ser un número finito.",
        });
      } else if (el.x < 0 || el.x > data.width) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["elements", i, "x"],
          message: `x debe estar entre 0 y ${data.width}.`,
        });
      }
      if (!Number.isFinite(el.y)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["elements", i, "y"],
          message: "La coordenada y debe ser un número finito.",
        });
      } else if (el.y < 0 || el.y > data.height) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["elements", i, "y"],
          message: `y debe estar entre 0 y ${data.height}.`,
        });
      }
      if (el.rotation != null && !Number.isFinite(el.rotation)) {
        ctx.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["elements", i, "rotation"],
          message: "La rotación debe ser un número finito.",
        });
      }
    });
  });

// ---------------------------------------------------------------------------
// Exercise detail — server response schema
// ---------------------------------------------------------------------------

export const exerciseDetailSchema = exerciseListItemSchema
  .extend({
    how_to: z.string(),
    layout_ascii: z.string().nullable(),
    layout_alt: z.string().nullable(),
    /** Structured SVG layout (feature 019). Null for non-gymkhana or not-yet-backfilled rows. */
    layout_json: gymkhanaLayoutSchema.nullable(),
    confidence: z.string().nullable(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Session assembly — server response schema
// ---------------------------------------------------------------------------

export const techniqueSessionItemSchema = z
  .object({
    exercise_id: z.number(),
    name: z.string(),
    segment: sessionSegmentSchema,
    position: z.number(),
    age_bands: z.array(ageBandSchema),
    skills: z.array(skillRefSchema),
    // Phase B (O-6): identifies the hidden synthetic combined-circuit item so
    // the UI can exclude it from "real exercise" lists/counts.
    is_hidden: z.boolean(),
    is_gymkhana: z.boolean(),
  })
  .strip();

export const assembleResultSchema = z
  .object({
    training_session_id: z.number(),
    mixes_age_bands: z.boolean(),
    items: z.array(techniqueSessionItemSchema),
    // Phase B (O-6): id of the synthetic hidden exercise created/updated for the
    // combined layout. Null when no combined_layout was provided in the request.
    combined_exercise_id: z.number().nullable().optional(),
  })
  .strip();

export const sessionItemsSchema = z.array(techniqueSessionItemSchema);

/**
 * Respuesta de POST /api/technique/sessions/{id}/exercises (feature 032, T007).
 * Mismo shape que assembleResultSchema, sin training_session_id/combined_exercise_id
 * (contracts/attach-technique-to-session.md) — items es la lista completa
 * actual, no solo el delta recién insertado.
 */
export const attachExercisesResponseSchema = z
  .object({
    mixes_age_bands: z.boolean(),
    items: z.array(techniqueSessionItemSchema),
  })
  .strip();

// ---------------------------------------------------------------------------
// Per-athlete skill progress — server response schemas
// ---------------------------------------------------------------------------

export const skillProgressEventSchema = z
  .object({
    id: z.number(),
    skill: skillRefSchema,
    status: skillProgressStatusSchema,
    coach_note: z.string().nullable(),
    season: z.number(),
    recorded_at: z.string(),
  })
  .strip();

const currentSkillProgressSchema = z
  .object({
    skill: skillRefSchema,
    status: skillProgressStatusSchema,
    recorded_at: z.string(),
    coach_note: z.string().nullable(),
  })
  .strip();

export const athleteProgressSchema = z
  .object({
    athlete_id: z.number(),
    current: z.array(currentSkillProgressSchema),
    history: z.array(skillProgressEventSchema),
  })
  .strip();

// ---------------------------------------------------------------------------
// Curation — server response schemas (reuse exerciseDetailSchema)
// ---------------------------------------------------------------------------

// Response for PATCH /visibility
export const visibilityResponseSchema = z
  .object({
    id: z.number(),
    is_hidden: z.boolean(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Form / input schemas (used with zodResolver)
// ---------------------------------------------------------------------------

/** Filtros del catálogo — validación de formulario de filtros. */
export const catalogFiltersSchema = z
  .object({
    skill: z.string().optional(),
    age_band: ageBandSchema.optional(),
    difficulty: difficultySchema.optional(),
    materials: z.string().optional(),
    include_hidden: z.boolean().optional(),
    is_game: z.boolean().optional(),
  })
  .strip();

const sessionItemInputSchema = z
  .object({
    exercise_id: z.number().int().positive(),
    segment: sessionSegmentSchema,
    position: z.number().int().min(1),
  })
  .strip();

/** Armar sesión — validación de formulario (US3). */
export const assembleSessionSchema = z
  .object({
    scheduled_date: z.string().min(1, "La fecha es obligatoria."),
    scheduled_start_time: z
      .string()
      .min(1, "La hora de inicio es obligatoria."),
    duration_min: z
      .number({ error: "Ingresa la duración en minutos." })
      .int()
      .min(10, "La duración mínima es 10 minutos."),
    location: z.string().min(1, "El lugar es obligatorio."),
    technical_focus: z.string().min(1, "El foco técnico es obligatorio."),
    objectives: z.string().optional().default(""),
    convocados_athlete_ids: z
      .array(z.number().int().positive())
      .min(1, "Convoca al menos un atleta."),
    items: z
      .array(sessionItemInputSchema)
      .min(1, "Agrega al menos un ejercicio a la sesión."),
  })
  .strip();

/** Registro de progreso — validación de formulario (US4). */
export const progressInputSchema = z
  .object({
    skill_id: z
      .number({ error: "Selecciona una habilidad." })
      .int()
      .positive("Selecciona una habilidad."),
    status: skillProgressStatusSchema,
    coach_note: z.string().max(500, "Máximo 500 caracteres.").optional(),
    season: z
      .number({ error: "El año de temporada es obligatorio." })
      .int()
      .min(2020)
      .max(2100),
  })
  .strip();

/** Crear ejercicio personalizado — validación de formulario (US5).
 *
 * Refinements:
 *  - gymkhana => layout_ascii requerido
 *  - ≥1 age band
 *  - ≥1 skill slug
 *
 * NOTE: The base object schema is exported separately so that
 * exerciseUpdateSchema can call .partial() before adding its own refinement.
 * In Zod v4, .partial() cannot be called on a schema that already has a
 * .superRefine() attached — it must be applied to the plain object schema first.
 */
const _exerciseCreateBaseSchema = z
  .object({
    name: z
      .string()
      .min(2, "El nombre debe tener al menos 2 caracteres.")
      .max(120, "El nombre no puede superar 120 caracteres."),
    summary: z
      .string()
      .min(5, "El resumen debe tener al menos 5 caracteres.")
      .max(500, "El resumen no puede superar 500 caracteres."),
    how_to: z.string().min(10, "Las instrucciones deben tener al menos 10 caracteres."),
    difficulty: difficultySchema,
    is_game: z.boolean().default(false),
    is_gymkhana: z.boolean().default(false),
    layout_ascii: z.string().optional().nullable(),
    layout_alt: z.string().optional().nullable(),
    age_bands: z
      .array(ageBandSchema)
      .min(1, "Selecciona al menos una franja de edad."),
    skill_slugs: z
      .array(z.string().min(1))
      .min(1, "Selecciona al menos una habilidad."),
    material_slugs: z.array(z.string()).default([]),
  })
  .strip();

export const exerciseCreateSchema = _exerciseCreateBaseSchema.superRefine(
  (data, ctx) => {
    if (data.is_gymkhana && !data.layout_ascii?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["layout_ascii"],
        message:
          "Los ejercicios de gymkhana requieren el diagrama en ASCII.",
      });
    }
  },
);

/** Editar ejercicio — todos los campos opcionales, mismas reglas de gymkhana.
 *
 * Derives from the base object schema (before superRefine) so that .partial()
 * is legal in Zod v4.
 */
export const exerciseUpdateSchema = _exerciseCreateBaseSchema
  .partial()
  .superRefine((data, ctx) => {
    if (data.is_gymkhana === true && !data.layout_ascii?.trim()) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["layout_ascii"],
        message:
          "Los ejercicios de gymkhana requieren el diagrama en ASCII.",
      });
    }
    if (data.age_bands !== undefined && data.age_bands.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["age_bands"],
        message: "Selecciona al menos una franja de edad.",
      });
    }
    if (data.skill_slugs !== undefined && data.skill_slugs.length === 0) {
      ctx.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["skill_slugs"],
        message: "Selecciona al menos una habilidad.",
      });
    }
  });

// Inferred form types (convenience re-exports for components)
export type CatalogFiltersForm = z.infer<typeof catalogFiltersSchema>;
export type AssembleSessionForm = z.infer<typeof assembleSessionSchema>;
export type ProgressInputForm = z.infer<typeof progressInputSchema>;
export type ExerciseCreateForm = z.infer<typeof exerciseCreateSchema>;
export type ExerciseUpdateForm = z.infer<typeof exerciseUpdateSchema>;
