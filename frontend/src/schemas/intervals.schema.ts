/**
 * Schemas de validación del módulo Entrenamiento por Intervalos (feature 026).
 *
 * Mirroring de convenciones de `schemas/strength.schemas.ts` (feature 021).
 *
 * Fuente única de verdad de las formas de datos: los tipos de dominio en
 * `types/intervals.types.ts` se infieren de estos schemas (`z.infer`).
 *
 * - Schemas de respuesta del servidor → `.parse()` en `api/intervals.ts`.
 * - Schemas de formulario → `zodResolver` en los componentes (tareas posteriores).
 *
 * Invariantes no negociables reflejadas aquí:
 * - Cadencia objetivo `>= 60` rpm para toda categoría (FR-004, sin excepción).
 * - `duration_s > 0` en cada bloque.
 * - Grupos de repetición: `repeat_count >= 2` e idéntico dentro del grupo (FR-002).
 * - Sin columna de potencia/watts: las únicas dimensiones objetivo son zona FC + cadencia.
 */

import { z } from "zod";

// ---------------------------------------------------------------------------
// Enums compartidos
// ---------------------------------------------------------------------------

/** Categoría por edad — reutiliza `AgeBand` del backend; intervalos solo usa `10-12`/`13-15`. */
export const intervalAgeBandSchema = z.enum(["10-12", "13-15"]);

/** Tipo de bloque de la estructura (FR-002). */
export const intervalBlockTypeSchema = z.enum([
  "warmup",
  "work",
  "recovery",
  "cooldown",
]);

/** Zona de frecuencia cardíaca objetivo (Z1..Z5). No existe objetivo de potencia (FR-005, D2). */
export const hrZoneSchema = z.enum(["Z1", "Z2", "Z3", "Z4", "Z5"]);

/** Estado global de la comparación plan-vs-real (todos son estados de UI, nunca errores crudos). */
export const matchOverallStatusSchema = z.enum([
  "computed",
  "no_activity",
  "computing",
  "failed",
]);

/** Estado de cumplimiento por bloque (badge: verde/ámbar/gris — Constitución III). */
export const blockMatchStatusSchema = z.enum([
  "cumplido",
  "fuera_tolerancia",
  "sin_dato",
]);

/** Qué disparó el cálculo de la comparación (observabilidad). */
export const matchTriggerSchema = z.enum([
  "link",
  "structure_change",
  "manual",
]);

/** Marca de dispositivo para el instructivo PDF (US3). */
export const instructivoBrandSchema = z.enum([
  "garmin",
  "magene",
  "igpsport",
]);

// ---------------------------------------------------------------------------
// Bloque — schema de entrada (formulario) compartido por estructuras y templates
// ---------------------------------------------------------------------------

export const intervalBlockInputSchema = z.object({
  position: z.number().int().min(1),
  block_type: intervalBlockTypeSchema,
  duration_s: z
    .number({ error: "La duración es obligatoria." })
    .int()
    .gt(0, "La duración debe ser mayor a 0 segundos."),
  target_zone: hrZoneSchema,
  target_cadence_rpm: z
    .number({ error: "La cadencia es obligatoria." })
    .int()
    .min(60, "La cadencia mínima es 60 rpm para todas las categorías."),
  repeat_group: z.number().int().positive().nullable().optional(),
  repeat_count: z
    .number()
    .int()
    .min(2, "Un grupo de repeticiones debe repetirse al menos 2 veces.")
    .nullable()
    .optional(),
});

/**
 * Refinamiento cruzado de grupos de repetición (FR-002 / código 422 `invalid_repeat_group`):
 * dentro de un mismo `repeat_group`, todos los bloques deben declarar `repeat_count`,
 * ser `>= 2`, e idéntico en todo el grupo. Emite issues por bloque en `repeat_count`.
 */
function refineRepeatGroups(
  blocks: readonly z.infer<typeof intervalBlockInputSchema>[],
  ctx: z.RefinementCtx,
): void {
  const groups = new Map<number, number[]>();
  blocks.forEach((block, index) => {
    if (block.repeat_group == null) return;
    const members = groups.get(block.repeat_group) ?? [];
    members.push(index);
    groups.set(block.repeat_group, members);
  });

  for (const indices of groups.values()) {
    const counts = indices.map((i) => blocks[i].repeat_count);
    const reference = counts.find((c) => c != null) ?? null;
    for (const index of indices) {
      const count = blocks[index].repeat_count;
      if (count == null) {
        ctx.addIssue({
          code: "custom",
          path: ["blocks", index, "repeat_count"],
          message:
            "Los bloques de un grupo de repetición deben indicar cuántas veces se repiten.",
        });
        continue;
      }
      if (count < 2) {
        ctx.addIssue({
          code: "custom",
          path: ["blocks", index, "repeat_count"],
          message: "Un grupo de repeticiones debe repetirse al menos 2 veces.",
        });
        continue;
      }
      if (reference != null && count !== reference) {
        ctx.addIssue({
          code: "custom",
          path: ["blocks", index, "repeat_count"],
          message:
            "Todos los bloques del mismo grupo deben repetirse el mismo número de veces.",
        });
      }
    }
  }
}

// ---------------------------------------------------------------------------
// Estructuras — schemas de entrada (formulario)
// ---------------------------------------------------------------------------

/** POST /api/intervals/structures — crea una estructura adjunta a una sesión (US1). */
export const intervalStructureCreateInputSchema = z
  .object({
    training_session_id: z.number().int().positive(),
    target_age_band: intervalAgeBandSchema,
    age_gate_confirmed: z.boolean().default(false),
    blocks: z
      .array(intervalBlockInputSchema)
      .min(1, "Agregá al menos un bloque a la estructura."),
  })
  .superRefine((data, ctx) => refineRepeatGroups(data.blocks, ctx));

/** PUT /api/intervals/structures/{id} — reemplazo completo (body sin `training_session_id`). */
export const intervalStructureUpdateInputSchema = z
  .object({
    target_age_band: intervalAgeBandSchema,
    age_gate_confirmed: z.boolean().default(false),
    blocks: z
      .array(intervalBlockInputSchema)
      .min(1, "Agregá al menos un bloque a la estructura."),
  })
  .superRefine((data, ctx) => refineRepeatGroups(data.blocks, ctx));

// ---------------------------------------------------------------------------
// Templates — schemas de entrada (formulario, US4)
// ---------------------------------------------------------------------------

/** POST/PUT /api/intervals/templates — crea/edita un template reutilizable. */
export const intervalTemplateSaveInputSchema = z
  .object({
    name: z.string().min(1, "El nombre es obligatorio.").max(120),
    target_age_band: intervalAgeBandSchema,
    mesocycle_phase: z.string().min(1, "La fase de mesociclo es obligatoria."),
    competition_proximity: z
      .string()
      .min(1, "La proximidad a competencia es obligatoria."),
    blocks: z
      .array(intervalBlockInputSchema)
      .min(1, "Agregá al menos un bloque al template."),
  })
  .superRefine((data, ctx) => refineRepeatGroups(data.blocks, ctx));

/** Filtros del listado de templates (US4-AC2), club-scoped en servidor. */
export const intervalTemplateFiltersSchema = z
  .object({
    age_band: intervalAgeBandSchema.optional(),
    mesocycle_phase: z.string().optional(),
    competition_proximity: z.string().optional(),
    include_archived: z.boolean().optional(),
  })
  .strip();

/** POST /api/intervals/templates/{id}/attach — clona el template en una sesión (copy-on-attach). */
export const intervalAttachInputSchema = z.object({
  training_session_id: z.number().int().positive(),
  age_gate_confirmed: z.boolean().default(false),
});

/** POST /api/intervals/structures/{id}/recalculate — recálculo manual (FR-015). */
export const intervalRecalculateInputSchema = z.object({
  activity_id: z.number().int().positive().optional(),
});

// ---------------------------------------------------------------------------
// Bloque — schema de respuesta del servidor
// ---------------------------------------------------------------------------

export const intervalBlockOutSchema = z
  .object({
    id: z.number(),
    position: z.number(),
    block_type: intervalBlockTypeSchema,
    duration_s: z.number(),
    target_zone: hrZoneSchema,
    target_cadence_rpm: z.number(),
    repeat_group: z.number().nullable(),
    repeat_count: z.number().nullable(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Estructuras — schema de respuesta del servidor (StructureOut)
// ---------------------------------------------------------------------------

export const intervalStructureOutSchema = z
  .object({
    id: z.number(),
    training_session_id: z.number(),
    target_age_band: intervalAgeBandSchema,
    age_gate_confirmed: z.boolean(),
    age_gate_confirmed_by: z.string().nullable(),
    age_gate_confirmed_at: z.string().nullable(),
    blocks: z.array(intervalBlockOutSchema),
    total_planned_duration_s: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Templates — schemas de respuesta del servidor (TemplateOut)
// ---------------------------------------------------------------------------

export const intervalTemplateOutSchema = z
  .object({
    id: z.number(),
    name: z.string(),
    target_age_band: intervalAgeBandSchema,
    mesocycle_phase: z.string(),
    competition_proximity: z.string(),
    is_archived: z.boolean(),
    blocks: z.array(intervalBlockOutSchema),
    total_planned_duration_s: z.number(),
    created_at: z.string(),
    updated_at: z.string(),
  })
  .strip();

export const intervalTemplateListSchema = z
  .object({
    items: z.array(intervalTemplateOutSchema),
    total: z.number(),
  })
  .strip();

// ---------------------------------------------------------------------------
// Matching — schemas de respuesta del servidor (detail-view payload, FR-017)
// ---------------------------------------------------------------------------

export const matchActivitySchema = z
  .object({
    id: z.number(),
    start_date_local: z.string(),
    elapsed_time_s: z.number(),
    sport_type: z.string(),
  })
  .strip();

/**
 * Fila de comparación por bloque aplanado. NUNCA contiene GPS/polyline/mapa ni
 * cadencia/potencia de la vuelta (Ley 1581, D4): solo duración/FC/velocidad media.
 */
export const matchBlockSchema = z
  .object({
    flat_index: z.number(),
    block_type: intervalBlockTypeSchema,
    repeat_iteration: z.number().nullable(),
    planned_duration_s: z.number(),
    target_zone: hrZoneSchema,
    target_cadence_rpm: z.number(),
    lap_index: z.number().nullable(),
    lap_elapsed_time_s: z.number().nullable(),
    lap_moving_time_s: z.number().nullable(),
    lap_average_heartrate: z.number().nullable(),
    lap_average_speed_m_s: z.number().nullable(),
    status: blockMatchStatusSchema,
  })
  .strip();

export const matchExtraLapSchema = z
  .object({
    lap_index: z.number(),
    elapsed_time_s: z.number(),
    average_heartrate: z.number().nullable(),
  })
  .strip();

export const matchSummarySchema = z
  .object({
    cumplido: z.number(),
    fuera_tolerancia: z.number(),
    sin_dato: z.number(),
    extra: z.number(),
  })
  .strip();

/**
 * Payload de la vista de detalle. Muchos campos son opcionales porque `status`
 * puede ser `no_activity` / `computing` / `failed` (sin bloques ni actividad).
 */
export const matchDetailSchema = z
  .object({
    structure_id: z.number(),
    status: matchOverallStatusSchema,
    activity: matchActivitySchema.nullish(),
    computed_at: z.string().nullish(),
    engine_version: z.number().nullish(),
    tolerance_pct: z.number().nullish(),
    blocks: z.array(matchBlockSchema).optional(),
    extra_laps: z.array(matchExtraLapSchema).optional(),
    summary: matchSummarySchema.nullish(),
    retry_available: z.boolean().optional(),
  })
  .strip();

/** POST recalculate → 202 `{ status: "computing" }`. */
export const matchRecalculateResponseSchema = z
  .object({
    status: z.string(),
  })
  .strip();
